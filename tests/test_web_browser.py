"""The web view in a real browser: the add dropdown and drag & drop. Skipped without playwright + a chromium."""
import os
import shutil
import socket
import subprocess
import sys
import time

import numpy as np
import pytest

sync_api = pytest.importorskip("playwright.sync_api")
httpx = pytest.importorskip("httpx")
pytest.importorskip("fastapi")

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

def _browser(p):
    for exe in (None, shutil.which("chromium"), shutil.which("chromium-browser"), shutil.which("google-chrome")):
        try:
            return p.chromium.launch(executable_path=exe, args=["--no-sandbox"]) if exe else p.chromium.launch()
        except Exception:
            continue
    pytest.skip("no chromium available")

@pytest.fixture(scope="module")
def page(tmp_path_factory):
    capture = tmp_path_factory.mktemp("data") / "capture.cf64"
    t = np.arange(250_000) / 250_000
    (np.exp(2j*np.pi*20_000*t) + 0.1*np.random.default_rng(0).standard_normal(t.size)).astype(np.complex64).tofile(capture)
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
    env = dict(os.environ, PYTHONPATH=os.path.join(ROOT, "src"))
    proc = subprocess.Popen([sys.executable, "-m", "pyspecan", "-v", "web", "-p", str(port), "-f", str(capture), "-d", "cf64", "-fs", "250k", "-n", "512"],
                            env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    try:
        for _ in range(100):
            try:
                httpx.get(f"http://127.0.0.1:{port}/api/status")
                break
            except Exception:
                time.sleep(0.1)
        with sync_api.sync_playwright() as p:
            browser = _browser(p)
            pg = browser.new_page(viewport={"width": 1500, "height": 900})
            errors = []
            pg.on("pageerror", lambda e: errors.append(str(e)))
            pg.goto(f"http://127.0.0.1:{port}/")
            pg.wait_for_selector(".plot")
            yield pg
            assert not errors, errors
            browser.close()
    finally:
        proc.terminate()
        proc.communicate(timeout=5)

def layout(page):
    return page.evaluate("[...document.querySelectorAll('.plot-row')].map(r => [...r.querySelectorAll('.plot-header b')].map(b => b.textContent))")

def plot(page, name):
    return page.locator(".plot", has=page.locator(f".plot-header b:text-is('{name}')"))

AT = {"left": (.1, .5), "right": (.9, .5), "above": (.5, .1), "below": (.5, .9)}

def drop(page, src, dst, where):
    box = plot(page, dst).bounding_box()
    plot(page, src).locator(".plot-header .grip").drag_to(plot(page, dst), target_position={"x": AT[where][0]*box["width"], "y": AT[where][1]*box["height"]})
    page.wait_for_timeout(400)

def test_add_dropdown_then_drag_and_drop(page):
    options = page.eval_on_selector_all("#sel-add-plot option", "o => o.map(x => x.textContent)")
    assert options[0].startswith("+") and {"PSD", "Spectrogram", "Persistence", "IQ"} <= set(options)
    for name in ("Spectrogram", "IQ", "Persistence"):
        page.select_option("#sel-add-plot", name)
        page.wait_for_function(f"[...document.querySelectorAll('.plot-header b')].some(b => b.textContent === '{name}')")
    assert layout(page) == [["PSD"], ["Spectrogram"], ["IQ"], ["Persistence"]]
    assert page.eval_on_selector("#sel-add-plot", "s => s.value") == ""

    drop(page, "IQ", "PSD", "right")
    assert layout(page) == [["PSD", "IQ"], ["Spectrogram"], ["Persistence"]]
    drop(page, "Persistence", "Spectrogram", "left")
    assert layout(page) == [["PSD", "IQ"], ["Persistence", "Spectrogram"]]
    drop(page, "Spectrogram", "PSD", "above")
    assert layout(page) == [["Spectrogram"], ["PSD", "IQ"], ["Persistence"]]
    drop(page, "Spectrogram", "IQ", "below")
    assert layout(page) == [["PSD", "IQ"], ["Spectrogram"], ["Persistence"]]
    drop(page, "Spectrogram", "Spectrogram", "left")     # onto itself
    assert layout(page) == [["PSD", "IQ"], ["Spectrogram"], ["Persistence"]]

def test_new_row_strip_and_indicators(page):
    assert not page.locator(".drop-tail").is_visible()
    box = plot(page, "PSD").locator(".plot-header").bounding_box()
    page.mouse.move(box["x"] + 60, box["y"] + 8)
    page.mouse.down()
    page.mouse.move(box["x"] + 80, box["y"] + 60, steps=4)
    page.wait_for_timeout(200)
    assert page.locator(".drop-tail").is_visible()
    target = plot(page, "Persistence").bounding_box()    # measured now, the strip shifted the layout
    x, y = target["x"] + target["width"]*.85, target["y"] + target["height"]/2
    page.mouse.move(x, y, steps=6); page.mouse.move(x + 1, y); page.wait_for_timeout(250)
    assert page.locator(".plot.drop-right").count() == 1
    strip = page.locator(".drop-tail").bounding_box()
    x, y = strip["x"] + strip["width"]/2, strip["y"] + strip["height"]/2
    page.mouse.move(x, y, steps=6); page.mouse.move(x + 1, y); page.wait_for_timeout(250)
    assert page.locator(".drop-tail.drop-end").count() == 1
    page.mouse.up()
    page.wait_for_timeout(400)
    assert layout(page) == [["IQ"], ["Spectrogram"], ["Persistence"], ["PSD"]]
    assert page.locator("[class*='drop-']:not(.drop-tail)").count() == 0 and not page.locator(".drop-tail").is_visible()

def test_header_buttons_and_removal_still_work(page):
    header = plot(page, "IQ").locator(".plot-header")
    header.locator("button", has_text="Pause").click()
    page.wait_for_timeout(300)
    assert header.locator("button", has_text="Resume").count() == 1
    header.locator("button[title='remove plot']").click()
    page.wait_for_timeout(300)
    assert layout(page) == [["Spectrogram"], ["Persistence"], ["PSD"]]

def test_layout_changes_are_not_stuck_behind_a_backlog_of_frames(page):
    """Playing the heavy persistence plot used to delay every other message by seconds"""
    page.click("#btn-start")
    page.wait_for_timeout(600)
    page.evaluate("""() => { window.__t = {}; document.addEventListener('drop', () => { window.__t.drop = performance.now(); window.__t.done = null; }, true);
        new MutationObserver(() => { if (window.__t.drop && !window.__t.done) window.__t.done = performance.now(); }).observe(document.getElementById('panels'), {childList: true}); }""")
    drop(page, "PSD", "Spectrogram", "right")
    t = page.evaluate("window.__t")
    assert t["done"] - t["drop"] < 600, t
    assert layout(page) == [["Spectrogram", "PSD"], ["Persistence"]]

def test_markers_menu_table_editor_and_spectrogram(page):
    if page.locator("#btn-stop").is_enabled():
        page.click("#btn-stop") # earlier tests may leave it playing, or at the end of the file
    page.click("#btn-reset")
    psd = plot(page, "PSD")
    assert psd.locator(".marker-editor").is_hidden() and psd.locator(".mtable").is_hidden()
    assert plot(page, "IQ").count() == 0 or plot(page, "IQ").locator("[id^=addmk-]").count() == 0 # not every plot has markers
    psd.locator("[id^=addmk-]").select_option("peak")
    psd.locator("[id^=addmk-]").select_option("channel")
    page.click("#btn-next")
    page.wait_for_function("document.querySelector('.plot .mtable:not([hidden]) td')")
    psd.locator(".marker-editor .mk-row").nth(1).wait_for() # the second add may still be on its way
    assert psd.locator(".marker-editor .mk-row").count() == 2
    cells = psd.locator(".mtable td").all_inner_texts()
    assert "peak" in cells and "channel" in cells
    # edit the channel's frequency in its row: the table follows
    row = psd.locator(".mk-row").nth(1)
    row.locator("label:has-text('Freq') input").fill("20k")
    row.locator("label:has-text('Freq') input").press("Enter")
    page.click("#btn-next")
    page.wait_for_function("[...document.querySelectorAll('.mtable td')].some((t) => t.textContent.startsWith('20 kHz'))")
    # the same menu on a spectrogram: a vertical line over the image, drawn in the marker's color
    spg = plot(page, "Spectrogram")
    spg.locator("[id^=addmk-]").select_option("point")
    page.click("#btn-next")
    page.wait_for_function("document.querySelectorAll('.mtable:not([hidden])').length >= 2")
    # remove from the editor
    psd.locator(".mk-row button").first.click()
    page.wait_for_function("document.querySelectorAll('.marker-editor .mk-row').length === 2")
    n = psd.locator("canvas").evaluate("""(c) => { const d = c.getContext('2d').getImageData(0, 0, c.width, c.height).data;
        let n = 0; for (let i = 0; i < d.length; i += 4) if (d[i] === 0x5c && d[i+1] === 0xb8 && d[i+2] === 0x5c) n++; return n; }""")
    assert n > 10 # GREEN: the channel's marker and band

def _psd_id(page):
    return page.evaluate("Object.keys(state.plots).find((k) => state.plots[k].name === 'PSD')")

def _markers(page, pid):
    return page.evaluate("(id) => state.plots[id].markers.map((m) => ({id: m.id, kind: m.kind, ...m.params}))", pid)

def _px(page, pid, hz, axis_y=0.5):
    """Page coordinates of frequency `hz` on the PSD canvas, `axis_y` of the way down the plot area"""
    return page.evaluate("""([id, hz, fy]) => { const rt = runtime[id], g = rt.geom[0], r = rt.canvas.getBoundingClientRect();
        return [r.left + g.x0 + (hz - g.xmin) / (g.xmax - g.xmin) * g.w, r.top + g.y0 + fy * g.h]; }""", [pid, hz, axis_y])

def _drag(page, a, b):
    page.mouse.move(*a); page.mouse.down(); page.mouse.move((a[0] + b[0]) / 2, (a[1] + b[1]) / 2, steps=4); page.mouse.move(*b, steps=4); page.mouse.up()

def test_markers_are_drawn_moved_and_resized_with_the_mouse(page):
    if page.locator("#btn-stop").is_enabled():
        page.click("#btn-stop")
    page.click("#btn-reset")
    page.click("#btn-next")
    pid = _psd_id(page)
    page.wait_for_function("(id) => runtime[id].frame && runtime[id].geom && runtime[id].geom[0]", arg=pid)
    while _markers(page, pid):  # start clean, earlier tests leave markers behind
        plot(page, "PSD").locator(".mk-row button").first.click()
        page.wait_for_timeout(250)
    assert page.evaluate("(id) => runtime[id].tool", pid) == "channel"

    # drag over a signal's left and right bounds: a channel marker appears there (20 kHz tone, 250 kHz span)
    _drag(page, _px(page, pid, 15_000), _px(page, pid, 25_000))
    page.wait_for_function("(id) => state.plots[id].markers.length === 1", arg=pid)
    m = _markers(page, pid)[0]
    assert m["kind"] == "channel" and abs(float(m["freq"]) - 20_000) < 1500 and abs(float(m["bw"]) - 10_000) < 2500, m
    page.wait_for_function("(id) => runtime[id].frame.axes[0].bands.some((b) => b.edit)", arg=pid)

    # resize: pull the right edge out to 35 kHz, the left edge stays
    band = page.evaluate("(id) => runtime[id].frame.axes[0].bands.find((b) => b.edit)", pid)
    _drag(page, _px(page, pid, band["hi"]), _px(page, pid, 35_000))
    page.wait_for_function("([id, bw]) => Math.abs(parseFloat(state.plots[id].markers[0].params.bw) - bw) > 3000", arg=[pid, float(m["bw"])])
    m2 = _markers(page, pid)[0]
    assert abs(float(m2["freq"]) + float(m2["bw"]) / 2 - 35_000) < 1500 and abs(float(m2["freq"]) - float(m2["bw"]) / 2 - band["lo"]) < 1500, (m2, band)

    # move: grab the body and drag it up in frequency, the width stays
    lo, hi = float(m2["freq"]) - float(m2["bw"]) / 2, float(m2["freq"]) + float(m2["bw"]) / 2
    _drag(page, _px(page, pid, (lo + hi) / 2), _px(page, pid, (lo + hi) / 2 + 40_000))
    page.wait_for_function("([id, f]) => Math.abs(parseFloat(state.plots[id].markers[0].params.freq) - f) > 20000", arg=[pid, float(m2["freq"])])
    m3 = _markers(page, pid)[0]
    assert abs(float(m3["freq"]) - float(m2["freq"]) - 40_000) < 2500 and abs(float(m3["bw"]) - float(m2["bw"])) < 1, (m3, m2)
    # the table follows (stopped: the edits redrew the block)
    page.wait_for_function("document.querySelector('.mtable td')")

    # a click with the point tool adds a point, which can then be dragged
    page.select_option(f"#tool-{pid}", "point")
    page.mouse.click(*_px(page, pid, -50_000, 0.3))
    page.wait_for_function("(id) => state.plots[id].markers.length === 2", arg=pid)
    pt = _markers(page, pid)[1]
    assert pt["kind"] == "point" and abs(float(pt["freq"]) + 50_000) < 2500, pt
    page.wait_for_function("(id) => runtime[id].frame.axes[0].markers.some((m) => m.edit === 'freq')", arg=pid)
    mark = page.evaluate("""(id) => { const rt = runtime[id], g = rt.geom[0], m = rt.frame.axes[0].markers.find((m) => m.edit === 'freq');
        const r = rt.canvas.getBoundingClientRect(), y = Math.min(Math.max(g.y0 + (1 - (m.y - g.ymin) / (g.ymax - g.ymin)) * g.h, g.y0 + 26), g.y0 + g.h);
        return [r.left + g.x0 + (m.x - g.xmin) / (g.xmax - g.xmin) * g.w, r.top + y - 7, m.x]; }""", pid)
    _drag(page, mark[:2], [mark[0] - 60, mark[1]])
    page.wait_for_function("([id, f]) => parseFloat(state.plots[id].markers[1].params.freq) < f - 5000", arg=[pid, float(pt["freq"])])
    assert len(_markers(page, pid)) == 2 # dragging a marker did not draw a new one

    # off: dragging over empty space draws nothing
    page.select_option(f"#tool-{pid}", "off")
    _drag(page, _px(page, pid, 80_000, 0.2), _px(page, pid, 100_000, 0.2))
    page.wait_for_timeout(500)
    assert len(_markers(page, pid)) == 2

def test_hover_shows_frequency_and_level_under_the_cursor(page):
    if page.locator("#btn-stop").is_enabled():
        page.click("#btn-stop")
    page.click("#btn-reset")
    page.click("#btn-next")
    pid = _psd_id(page)
    page.wait_for_function("(id) => runtime[id].geom && runtime[id].geom[0]", arg=pid)
    def readout_pixels():
        # the label box is in the top right of the plot area, its text is drawn in #eee
        return page.evaluate("""(id) => { const rt = runtime[id], g = rt.geom[0], c = rt.canvas, dpr = c.width / parseFloat(c.style.width);
            const d = c.getContext('2d').getImageData(Math.round((g.x0 + g.w - 190) * dpr), Math.round(g.y0 * dpr), Math.round(190 * dpr), Math.round(60 * dpr)).data;
            let n = 0; for (let i = 0; i < d.length; i += 4) if (d[i] >= 0xe0 && d[i+1] >= 0xe0 && d[i+2] >= 0xe0) n++; return n; }""", pid)
    page.mouse.move(5, 5) # away from the plot
    page.wait_for_timeout(300)
    base = readout_pixels() # whatever else is drawn in that corner
    page.mouse.move(*_px(page, pid, 20_000, 0.5))
    page.wait_for_timeout(300)
    assert page.evaluate("(id) => runtime[id].hover === true", pid)
    assert readout_pixels() > base + 100
    page.mouse.move(5, 5)
    page.wait_for_function("(id) => !runtime[id].hover", arg=pid)
    page.wait_for_timeout(200)
    assert readout_pixels() == base
