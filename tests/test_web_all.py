"""Every plot type and every marker kind in the web view, in a real browser: each one draws, says nothing went wrong,
and the server logs no error. Skipped without playwright + a chromium"""
import os
import socket
import subprocess
import sys
import threading
import time

import numpy as np
import pytest

sync_api = pytest.importorskip("playwright.sync_api")
httpx = pytest.importorskip("httpx")
pytest.importorskip("fastapi")

from test_web_browser import ROOT, _browser

FS = 1e6

def qpsk_capture(n=1_000_000, baud=50e3, f0=150e3, beta=0.35, seed=0) -> np.ndarray:
    """QPSK through a root raised cosine (shaped in frequency, numpy only) at f0, a tone at -200 kHz, and noise"""
    rng = np.random.default_rng(seed)
    sps = int(FS / baud)
    k = n // sps + 1
    up = np.zeros(k * sps, complex)
    up[::sps] = ((rng.integers(0, 2, k) * 2 - 1) + 1j * (rng.integers(0, 2, k) * 2 - 1)) / np.sqrt(2)
    f = np.abs(np.fft.fftfreq(len(up), 1 / FS)) / baud # in symbol rates
    rc = np.where(f <= (1 - beta) / 2, 1.0, np.where(f <= (1 + beta) / 2, 0.5 * (1 + np.cos(np.pi / beta * (f - (1 - beta) / 2))), 0.0))
    x = np.fft.ifft(np.fft.fft(up) * np.sqrt(rc))[:n]
    x /= np.sqrt(np.mean(np.abs(x)**2)) # unit power: the strongest signal, the one analysed
    t = np.arange(n) / FS
    x = x * np.exp(2j * np.pi * f0 * t) + 0.3 * np.exp(2j * np.pi * -200e3 * t)
    return (x + 0.02 * (rng.standard_normal(n) + 1j * rng.standard_normal(n))).astype(np.complex64)

@pytest.fixture(scope="module")
def page(tmp_path_factory):
    capture = tmp_path_factory.mktemp("data") / "qpsk.cf64"
    qpsk_capture().tofile(capture)
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
    env = dict(os.environ, PYTHONPATH=os.path.join(ROOT, "src"))
    proc = subprocess.Popen([sys.executable, "-m", "pyspecan", "-v", "web", "-p", str(port), "-f", str(capture), "-F", "cf64",
                             "-fs", "1M", "-n", "1024"], env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    log: list[str] = []
    reader = threading.Thread(target=lambda: log.extend(proc.stdout), daemon=True) # type: ignore[arg-type]
    reader.start()
    try:
        for _ in range(100):
            try:
                httpx.get(f"http://127.0.0.1:{port}/api/status")
                break
            except Exception:
                time.sleep(0.1)
        with sync_api.sync_playwright() as p:
            browser = _browser(p)
            pg = browser.new_page(viewport={"width": 1400, "height": 900})
            errors: list[str] = []
            pg.on("pageerror", lambda e: errors.append(str(e)))
            pg.goto(f"http://127.0.0.1:{port}/")
            pg.wait_for_selector(".plot")
            pg.server_log = log # type: ignore[attr-defined]
            yield pg
            assert not errors, errors
            browser.close()
    finally:
        proc.terminate()
        proc.wait(timeout=5)
    bad = [line for line in log if "Traceback" in line or " ERROR " in line or "Error:" in line]
    assert not bad, "".join(log[-60:])

def _ids(page) -> list[str]:
    return page.evaluate("Object.keys(state.plots)")

def _drawn(page, pid) -> int:
    """Pixels the plot's canvas painted brighter than the background"""
    return page.evaluate("""(id) => { const c = runtime[id].canvas, d = c.getContext('2d').getImageData(0, 0, c.width, c.height).data;
        let n = 0; for (let i = 0; i < d.length; i += 4) if (d[i] + d[i+1] + d[i+2] > 120) n++; return n; }""", pid)

def _message(page) -> str:
    return page.evaluate("document.getElementById('lbl-message').textContent")

def _clear(page):
    """No plots, the file back at its start (the capture is only 20 blocks)"""
    for pid in _ids(page):
        page.evaluate("(id) => plotOp('del', {id})", pid)
    page.wait_for_function("Object.keys(state.plots).length === 0")
    if page.locator("#btn-stop").is_enabled():
        page.click("#btn-stop")
    page.click("#btn-reset")

def test_every_plot_type_draws(page):
    from pyspecan.plots.settings import HAVE_RPPS
    types = page.evaluate("state.plot_types")
    assert {"3D Spectrogram", "IQ 3D", "Phase Noise", "Analog Demod"} <= set(types) # the web view draws 3d now
    if HAVE_RPPS:
        assert {"3D Constellation", "Constellation", "Eye Diagram", "Network Analyzer", "Impulse Response", "Cyclic Spectrum",
                "Symbol Table", "Error Vector", "Error Vector Spectrum"} <= set(types)
    problems = []
    for name in types:
        _clear(page)
        page.select_option("#sel-add-plot", name)
        page.wait_for_function("Object.keys(state.plots).length === 1")
        pid = _ids(page)[0]
        for _ in range(3):
            page.click("#btn-next")
            page.wait_for_timeout(250)
        try:
            page.wait_for_function("(id) => runtime[id] && runtime[id].frame && runtime[id].geom && runtime[id].geom.length", arg=pid, timeout=8000)
        except Exception:
            problems.append(f"{name}: no frame")
            continue
        frame = page.evaluate("(id) => runtime[id].frame", pid)
        drawn = _drawn(page, pid)
        has_data = any(a["traces"] or a.get("image") for a in frame["axes"])
        readout = dict(frame.get("readout") or [])
        if drawn < 500:
            problems.append(f"{name}: drew {drawn} pixels")
        if not has_data:
            problems.append(f"{name}: no traces or image ({readout})")
        if "Lock" in readout: # a DSP plot that found the QPSK should have locked to it
            problems.append(f"{name}: {readout['Lock']}")
        if "rror" in _message(page):
            problems.append(f"{name}: {_message(page)}")
    _clear(page)
    assert not problems, problems

def test_3d_axes_turn_with_the_mouse(page):
    _clear(page)
    page.select_option("#sel-add-plot", "IQ 3D")
    page.wait_for_function("Object.keys(state.plots).length === 1")
    pid = _ids(page)[0]
    page.click("#btn-next")
    page.wait_for_function("(id) => runtime[id].geom && runtime[id].geom[0] && runtime[id].geom[0].is3d", arg=pid)
    box = page.evaluate("(id) => runtime[id].canvas.getBoundingClientRect().toJSON()", pid)
    cx, cy = box["x"] + box["width"] / 2, box["y"] + box["height"] / 2
    before = page.evaluate("(id) => ({...runtime[id].view3d[0]})", pid)
    page.mouse.move(cx, cy)
    page.mouse.down()
    page.mouse.move(cx + 100, cy + 40, steps=5)
    page.mouse.up()
    after = page.evaluate("(id) => ({...runtime[id].view3d[0]})", pid)
    assert after["az"] == pytest.approx(before["az"] - 50) and after["el"] == pytest.approx(before["el"] + 20)
    page.mouse.dblclick(cx, cy)
    assert page.evaluate("(id) => runtime[id].view3d[0]", pid) == before # a double click resets it
    _clear(page)

def test_every_marker_kind_measures(page):
    _clear(page)
    page.select_option("#sel-add-plot", "PSD")
    page.wait_for_function("Object.keys(state.plots).length === 1")
    pid = _ids(page)[0]
    kinds = page.evaluate("(id) => Object.keys(state.plots[id].marker_kinds)", pid)
    assert {"peaks", "harmonics", "toi", "limit"} <= set(kinds)
    for k, kind in enumerate(kinds, 1):
        page.select_option(f"#addmk-{pid}", kind)
        page.wait_for_function("([id, n]) => state.plots[id].markers.length === n", arg=[pid, k])
    page.click("#btn-next")
    page.wait_for_function("([id, n]) => runtime[id].frame && runtime[id].frame.table && new Set(runtime[id].frame.table.rows.filter((r) => r.id).map((r) => r.id)).size === n",
                           arg=[pid, len(kinds)])
    rows = page.evaluate("(id) => runtime[id].frame.table.rows.filter((r) => r.id).map((r) => r.cells.join(' '))", pid)
    assert all("Error" not in r and "rror" not in r for r in rows), rows
    assert page.locator(f"#plot-{pid} .mtable td").count() if page.locator(f"#plot-{pid}").count() else True
    limit = page.evaluate("(id) => runtime[id].frame.axes[0].markers.find((m) => m.kind === 'hline' && m.edit === 'level')", pid)
    assert limit is not None # the limit line, to drag
    _clear(page)

def test_phase_noise_has_a_log_axis(page):
    _clear(page)
    page.select_option("#sel-add-plot", "Phase Noise")
    page.wait_for_function("Object.keys(state.plots).length === 1")
    pid = _ids(page)[0]
    for _ in range(2):
        page.click("#btn-next")
        page.wait_for_timeout(200)
    page.wait_for_function("(id) => runtime[id].geom && runtime[id].geom[0] && runtime[id].geom[0].xlog", arg=pid)
    g = page.evaluate("(id) => runtime[id].geom[0]", pid)
    # the pixel of a decade sits where log spacing puts it
    x = page.evaluate("([id, v]) => pixX(runtime[id].geom[0], v)", [pid, 10 ** ((np.log10(g["xmin"]) + np.log10(g["xmax"])) / 2)])
    assert x == pytest.approx(g["x0"] + g["w"] / 2, abs=1)
    _clear(page)
