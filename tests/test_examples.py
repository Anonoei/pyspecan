"""The worked examples in examples/ run and their own checks pass

Each one is a script that asserts what it shows; this runs it as `python examples/<name>.py` would. dsp.py says it
has nothing to do without rpps and stops. launch.py opens a view: it runs here with the console view, which ends when
its input does."""
import os
import runpy
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
EXAMPLES = ROOT / "examples"

RUN = ["quickstart", "layout", "extension", "dsp"]

@pytest.fixture
def registries():
    """What an example registers (extension.py: a plot and a marker kind) is dropped after it, so the other tests
    see only pyspecan's own"""
    from pyspecan.plots import MARKER_KINDS, PLOTS
    before = {reg: set(reg.names()) for reg in (PLOTS, MARKER_KINDS)}
    yield
    for reg, names in before.items():
        for name in set(reg.names()) - names:
            reg.unregister(name)

@pytest.mark.parametrize("name", RUN)
def test_example(name, monkeypatch, registries):
    path = str(EXAMPLES / f"{name}.py")
    monkeypatch.setattr("sys.argv", [path]) # the script's own defaults, not pytest's arguments
    runpy.run_path(path, run_name="__main__")

def test_launch_console():
    env = {**os.environ, "PYTHONPATH": str(ROOT / "src")}
    r = subprocess.run([sys.executable, str(EXAMPLES / "launch.py"), "cui"], input="step\nquit\n", text=True,
                       capture_output=True, timeout=60, env=env, cwd=ROOT, check=False)
    assert r.returncode == 0, r.stderr
    assert "tone.cf32" in r.stdout

def test_every_example_is_run():
    """A new example joins RUN (or is launched above)"""
    have = {p.stem for p in EXAMPLES.glob("*.py")}
    assert have == set(RUN) | {"launch"}
