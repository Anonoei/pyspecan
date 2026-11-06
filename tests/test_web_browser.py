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
    plot(page, src).locator(".plot-header").drag_to(plot(page, dst), target_position={"x": AT[where][0]*box["width"], "y": AT[where][1]*box["height"]})
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
