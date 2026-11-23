"""Screenshots for the README: the views (web, tkGUI, console), their plots and features, on a synthetic capture

    python tools/screenshots.py                  # every scene into media/
    python tools/screenshots.py --only web       # one view (web, tk, cui)
    python tools/screenshots.py --scene dsp      # scenes whose name holds "dsp"
    python tools/screenshots.py --list           # what it would take

The captures are made here (numpy only, tools/demo.py), so the pictures are the same every time: a QPSK signal, an FM
broadcast-like carrier, a clean carrier with phase noise, two tones with their third order products, a bursty signal,
a slow chirp, and noise; for the scenes of signals cut in time, TDMA bursts, a hopper and a framed carrier. Each scene
is a
layout (the same --plot / --row items the command line takes), a few blocks stepped, and sometimes something done
with the mouse (a 3D plot turned, the cursor readout shown).

Needs: playwright with a chromium (web), a display (tk), pillow (the tk window grab and the console's text drawn as
an image). The DSP scenes need rpps (pip install pyspecan[dsp]) and are skipped without it.
"""
import argparse
import contextlib
import io
import os
import pathlib
import re
import socket
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass, field

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))


import demo  # noqa: E402 (the synthetic captures, shared with benchmark.py)


# --- scenes --- #
@dataclass
class Scene:
    name: str            # file name: media/<view>_<name>.png
    view: str            # web, tk, cui
    plots: list          # layout items: "PSD marker=peak", None for a new row
    steps: int = 6       # blocks read before the picture
    args: list = field(default_factory=list) # more command line arguments (globals)
    dsp: bool = False    # needs rpps
    turn: int | None = None  # web: drag this plot's canvas (a 3d plot turned)
    hover: tuple | None = None # web: (plot index, x, y) the cursor rests on, fractions of the canvas
    store_ref: int | None = None # after this many blocks, press every plot's "store ref" (then step the rest)
    menu: str | None = None  # web: open "+ Add plot" and point at this plot (its description shows)
    capture: str = "capture" # the tools/demo.py capture it runs on
    size: tuple = (1600, 1000)

DSP = ["--dsp_freq", "150k", "--dsp_bw", "60k"]
SCENES = [
    Scene("spectrum", "web", ["PSD marker=signals marker=peak", "Spectrogram max_count=40", None, "Persistence show_max=on",
                              "Surface Spectrogram max_count=32"], steps=34, hover=(0, 0.62, 0.35)),
    Scene("measurements", "web", ["PSD marker=channel:freq=150k,bw=60k marker=toi:f1=-120k,f2=-100k marker=limit:level=-45",
                                  "Phase Noise carrier=-420k pn_nfft=16384", None,
                                  "Analog Demod mode=FM carrier=-300k demod_bw=40k", "CCDF"], steps=8),
    Scene("analysis", "web", ['PSD "math=live - ref"', "Scalogram", None, "Vector Diagram", "Constellation Density"], steps=10,
          store_ref=3, args=DSP, dsp=True),
    Scene("picker", "web", ["PSD marker=signals", "Spectrogram max_count=40"], steps=20, menu="Eye Diagram"),
    Scene("time", "web", ["Scope trig_mode=auto", "Frequency vs Time", None, "IQ Density", "Power vs Time"], steps=6),
    Scene("3d", "web", ["3D Spectrogram", "IQ 3D", None, "Surface Spectrogram cmap=hot max_count=32", "Occupancy"], steps=34, turn=2),
    Scene("dsp", "web", ["PSD marker=signals", "Constellation", None, "Eye Diagram", "Network Analyzer"], steps=6, args=DSP, dsp=True),
    Scene("vsa", "web", ["3D Constellation", "Error Vector", None, "Impulse Response", "Cyclic Spectrum"], steps=6, args=DSP, dsp=True),
    Scene("bursts", "web", ["PSD trig_mode=gated vbw=0 t1_mode=average marker=signals", "Waveform ID", None, "Bursts", "Hopping"],
          steps=8, args=["--dsp_freq=-250k", "--dsp_bw", "140k"], dsp=True, capture="structured"),
    Scene("frames", "web", ["Marker Trend marker=channel:freq=300k,bw=70k marker=obw:freq=300k,span=100k", "Autocorrelation span=12m scale=dB", None,
                            "Frame Raster", "Signal Profile"],
          steps=14, args=["--dsp_freq", "300k", "--dsp_bw", "70k"], dsp=True, capture="structured"),
    Scene("spectrum", "tk", ["PSD marker=peak marker=obw:freq=150k,span=100k", "Spectrogram max_count=40", None,
                             "Persistence show_max=on", "3D Spectrogram"], steps=30),
    Scene("dsp", "tk", ["PSD marker=signals", "Constellation", None, "Eye Diagram", "Error Vector"], steps=6, args=DSP, dsp=True),
    Scene("spectrum", "cui", ["PSD marker=peak", "Spectrogram max_count=24"], steps=26, size=(150, 48)),
]

def plot_args(items: list) -> list[str]:
    out = []
    for it in items:
        out += ["--row"] if it is None else ["--plot", it]
    return out

def have_rpps() -> bool:
    from pyspecan.plots.settings import HAVE_RPPS
    return HAVE_RPPS

# --- web --- #
def shoot_web(scene: Scene, cap: pathlib.Path, out: pathlib.Path):
    from playwright.sync_api import sync_playwright
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
    env = dict(os.environ, PYTHONPATH=str(ROOT / "src"))
    cmd = [sys.executable, "-m", "pyspecan", "-v", "web", "-p", str(port), "-f", str(cap), "-F", "cf32", "-fs", "1M", "-n", "1024",
           *plot_args(scene.plots), *scene.args]
    proc = subprocess.Popen(cmd, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True)
    try:
        import urllib.request
        for _ in range(150):
            try:
                urllib.request.urlopen(f"http://127.0.0.1:{port}/api/status", timeout=1)
                break
            except OSError:
                time.sleep(0.1)
        with sync_playwright() as p:
            browser = p.chromium.launch(args=["--no-sandbox"])
            page = browser.new_page(viewport={"width": scene.size[0], "height": scene.size[1]}, device_scale_factor=1)
            errors = []
            page.on("pageerror", lambda e: errors.append(str(e)))
            page.goto(f"http://127.0.0.1:{port}/")
            page.wait_for_selector(".plot")
            for k in range(scene.steps):
                if k == scene.store_ref:
                    for b in page.locator("button.plot-action", has_text="store ref").all():
                        b.click()
                    page.wait_for_timeout(300)
                page.click("#btn-next")
                page.wait_for_timeout(200)
            page.wait_for_timeout(600)
            canvases = page.locator(".plot canvas")
            if scene.turn is not None:
                box = canvases.nth(scene.turn).bounding_box()
                cx, cy = box["x"] + box["width"] / 2, box["y"] + box["height"] / 2
                page.mouse.move(cx, cy)
                page.mouse.down()
                page.mouse.move(cx + 40, cy - 10, steps=6)
                page.mouse.up()
                page.mouse.move(5, 5)
            if scene.menu is not None:
                page.click("#btn-add-plot")
                page.locator(f".add-menu-item[data-name='{scene.menu}']").hover()
            if scene.hover is not None:
                k, fx, fy = scene.hover
                box = canvases.nth(k).bounding_box()
                page.mouse.move(box["x"] + box["width"] * fx, box["y"] + box["height"] * fy)
            page.wait_for_timeout(400)
            page.screenshot(path=str(out))
            browser.close()
        if errors:
            raise RuntimeError(f"page errors: {errors}")
    finally:
        proc.terminate()
        err = proc.communicate(timeout=10)[1]
    if "Traceback" in err:
        raise RuntimeError(err[-2000:])

# --- tk --- #
def shoot_tk(scene: Scene, cap: pathlib.Path, out: pathlib.Path):
    from PIL import ImageGrab

    from pyspecan.config import Sink, View
    from pyspecan.controller.controller import GetController
    from pyspecan.model.model import GetModel
    from pyspecan.view.view import GetView
    kw = dict(path=str(cap), fmt="cf32", Fs="1M", nfft=1024, layout_items=list(scene.plots), **_globals(scene.args))
    ctrl = GetController(View.tkGUI, Sink.FILE)(GetModel(Sink.FILE)(**kw), GetView(View.tkGUI, Sink.FILE)(**kw), **kw)
    root = ctrl.view.root
    errors = []
    root.report_callback_exception = lambda *a: errors.append(a)
    root.geometry(f"{scene.size[0]}x{scene.size[1]}+0+0")
    root.attributes("-topmost", True)
    def pump(seconds):
        end = time.monotonic() + seconds
        while time.monotonic() < end:
            root.update()
            time.sleep(0.01)
    try:
        pump(1.0)
        for pid, pane in ctrl.panels.panes.items(): # the plots, not their settings columns
            if pane.pane.fr_sets.winfo_manager():
                ctrl.panels.toggle_settings(pid)
        pump(0.3)
        rows = ctrl.panels.panel.main # rows of even height, columns of even width
        for k in range(len(rows.panes()) - 1):
            rows.sashpos(k, rows.winfo_height() * (k + 1) // len(rows.panes()))
        for row in ctrl.panels.rows:
            for k in range(len(row.main.panes()) - 1):
                row.main.sashpos(k, row.main.winfo_width() * (k + 1) // len(row.main.panes()))
        for k in range(scene.steps):
            if k == scene.store_ref:
                for pid, plot in list(ctrl.plots.plots.items()):
                    if "store ref" in plot.ACTIONS:
                        ctrl.plot_action(pid, "store ref")
            ctrl.command("next")
            pump(0.35)
        pump(0.8)
        x, y = root.winfo_rootx(), root.winfo_rooty()
        ImageGrab.grab(bbox=(x, y, x + root.winfo_width(), y + root.winfo_height())).save(out)
    finally:
        ctrl.quit()
    if errors:
        raise RuntimeError(f"tk errors: {errors}")

def _globals(args: list) -> dict:
    """--dsp_freq 150k ... -> {"dsp_freq": "150k", ...}"""
    return {args[k].lstrip("-"): args[k + 1] for k in range(0, len(args), 2)}

# --- console --- #
ANSI = re.compile(r"\x1b\[([0-9;]*)m")

def _mono_font(size: int):
    """A monospace font with braille (the console draws traces in braille), from fontconfig, else pillow's own"""
    from PIL import ImageFont
    for query in (":spacing=mono:charset=2800", ":spacing=mono"):
        try:
            path = subprocess.run(["fc-match", "-f", "%{file}", query], capture_output=True, text=True, check=True).stdout.strip()
            if path.endswith((".ttf", ".otf")):
                return ImageFont.truetype(path, size)
        except (OSError, subprocess.CalledProcessError):
            continue
    return ImageFont.load_default(size)

def ansi_image(text: str, font_size: int = 15, bg=(12, 12, 12), fg=(220, 220, 220)):
    """Text with 24-bit color escapes (the console view's output) drawn as an image"""
    from PIL import Image, ImageDraw
    font = _mono_font(font_size)
    cw = int(round(font.getlength("M")))
    ch = int(font_size * 1.25)
    lines = text.split("\n")
    width = max((len(ANSI.sub("", l)) for l in lines), default=1)
    img = Image.new("RGB", (width * cw + 20, len(lines) * ch + 20), bg)
    draw = ImageDraw.Draw(img)
    for row, line in enumerate(lines):
        col, cur_fg, cur_bg, dim, pos = 0, fg, None, False, 0
        for m in list(ANSI.finditer(line)) + [None]:
            end = m.start() if m else len(line)
            for chr_ in line[pos:end]:
                x, y = 10 + col * cw, 10 + row * ch
                if cur_bg is not None:
                    draw.rectangle([x, y, x + cw, y + ch], fill=cur_bg)
                color = tuple(int(c * 0.55) for c in cur_fg) if dim else cur_fg
                draw.text((x, y), chr_, font=font, fill=color)
                col += 1
            if m is None:
                break
            codes = [int(c) for c in m.group(1).split(";") if c] or [0]
            k = 0
            while k < len(codes):
                c = codes[k]
                if c == 0:
                    cur_fg, cur_bg, dim = fg, None, False
                elif c == 2:
                    dim = True
                elif c in (38, 48) and k + 4 < len(codes) + 0 and codes[k + 1] == 2:
                    rgb = tuple(codes[k + 2:k + 5])
                    if c == 38:
                        cur_fg = rgb
                    else:
                        cur_bg = rgb
                    k += 4
                k += 1
            pos = m.end()
    return img

def shoot_cui(scene: Scene, cap: pathlib.Path, out: pathlib.Path):
    from pyspecan.config import Sink, View
    from pyspecan.controller.controller import GetController
    from pyspecan.model.model import GetModel
    from pyspecan.view.view import GetView
    kw = dict(path=str(cap), fmt="cf32", Fs="1M", nfft=1024, layout_items=list(scene.plots), **_globals(scene.args))
    view = GetView(View.CUI, Sink.FILE)(**kw)
    ctrl = GetController(View.CUI, Sink.FILE)(GetModel(Sink.FILE)(**kw), view, **kw)
    view.size = lambda: scene.size # a terminal this big
    view.use_color = True
    view.tty = False
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        for _ in range(scene.steps):
            ctrl.command("next")
        buf.seek(0)
        buf.truncate()
        ctrl.draw()
    ansi_image(buf.getvalue().rstrip("\n")).save(out)

# --- main --- #
def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--out", default=str(ROOT / "media"), help="directory the pictures go in")
    ap.add_argument("--only", default="", help="views to take, comma separated: web, tk, cui")
    ap.add_argument("--scene", default="", help="only scenes whose name holds this")
    ap.add_argument("--list", action="store_true", help="list the scenes and exit")
    ap.add_argument("--child", nargs=2, metavar=("SCENE", "CAPTURE"), help=argparse.SUPPRESS) # one tk scene, in its own process
    a = ap.parse_args()
    if a.child: # a second Tk in one process trips over the first one's leftovers
        scene = next(s for s in SCENES if s.view == "tk" and s.name == a.child[0])
        shoot_tk(scene, pathlib.Path(a.child[1]), pathlib.Path(a.out) / f"tk_{scene.name}.png")
        return
    views = {v.strip() for v in a.only.split(",") if v.strip()}
    scenes = [s for s in SCENES if (not views or s.view in views) and a.scene in s.name]
    if a.list:
        for s in scenes:
            print(f"{s.view}_{s.name}: {' | '.join('/' if p is None else p for p in s.plots)}{'  (rpps)' if s.dsp else ''}")
        return
    out_dir = pathlib.Path(a.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    dsp = have_rpps()
    with tempfile.TemporaryDirectory() as tmp:
        caps = {}
        for name in sorted({s.capture for s in scenes}):
            caps[name] = pathlib.Path(tmp) / f"{name}.cf32"
            getattr(demo, name)().tofile(caps[name])
        failed = []
        for s in scenes:
            out = out_dir / f"{s.view}_{s.name}.png"
            if s.dsp and not dsp:
                print(f"skip {out.name}: needs rpps (pip install pyspecan[dsp])")
                continue
            t = time.monotonic()
            cap = caps[s.capture]
            try:
                if s.view == "tk":
                    subprocess.run([sys.executable, __file__, "--out", str(out_dir), "--child", s.name, str(cap)], check=True)
                else:
                    {"web": shoot_web, "cui": shoot_cui}[s.view](s, cap, out)
                print(f"{out} ({time.monotonic() - t:.1f} s)")
            except Exception as e: # one scene failing does not stop the others
                failed.append(out.name)
                print(f"FAILED {out.name}: {e}", file=sys.stderr)
    if failed:
        sys.exit(f"{len(failed)} failed: {', '.join(failed)}")

if __name__ == "__main__":
    main()
