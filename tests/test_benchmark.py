"""dev/benchmark.py: every plot timed against a PSD on the same blocks"""
import json
import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

def test_benchmark_writes_costs_in_psds(tmp_path):
    out = tmp_path / "benchmark.json"
    proc = subprocess.run([sys.executable, os.path.join(ROOT, "dev", "benchmark.py"), "--plots", "scope,spectrogram",
                           "--blocks", "3", "--warmup", "1", "--sweep", "10", "--markers", "--json", str(out)],
                          capture_output=True, text=True, timeout=300, check=False)
    assert proc.returncode == 0, proc.stderr
    assert "PSD reference" in proc.stdout and "x PSD" in proc.stdout and "declared" in proc.stdout and "Marker" in proc.stdout
    d = json.loads(out.read_text())
    assert d["reference"]["plot"] == "PSD" and d["config"]["block"] == 10000
    assert set(d["plots"]) == {"PSD", "Scope", "Spectrogram"} # the reference always runs
    assert all(r["median"] > 0 and r["first"] > 0 for r in d["plots"].values())
    assert "peak" in d["markers"] and "extra" in d["markers"]["peak"]
