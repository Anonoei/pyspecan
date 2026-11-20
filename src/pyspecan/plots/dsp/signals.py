"""The `signals` marker kind: rpps' signal search on a spectrum, a box on every signal it finds"""
import numpy as np

from ..frame import BLUE, GREEN, Band
from ..freq import fmt_hz, optional_float
from ..markers import MarkerKind, Result, marker_kind
from ..settings import Setting
from .analyzer import analyzer

EDIT = ("dsp_freq", "dsp_bw") # a box's center and width set the analysed signal (the "Analysis" globals)

@marker_kind("signals")
class Signals(MarkerKind):
    """Every signal found in the block, boxed from the noise floor to its peak. The one the DSP plots analyse is
    green: click another box to analyse it, drag a box's edges to adjust what is analysed"""
    COLOR = BLUE
    PARAMS = (
        Setting("min_snr", "Min SNR (dB)", "text", default="", coerce=optional_float, hint="auto",
                help="detection threshold above the noise floor, blank for the search's own"),
    )

    def evaluate(self, ctx, mid, p):
        an = analyzer(ctx.plot.source)
        sv = an.survey(float(p["min_snr"]) if p["min_snr"] else None)
        if sv is None:
            return Result([["-", "no samples"]])
        sel = an.selection(ctx.plot.dsp_freq, ctx.plot.dsp_bw)
        trace = np.asarray(ctx.trace)
        floor = float(np.median(trace))
        rows, bands, chosen_any = [], [], False
        for k, s in enumerate(sv, 1):
            lo, hi = s.cf + s.lo, s.cf + s.hi
            inside = (ctx.freqs >= lo) & (ctx.freqs <= hi)
            peak = float(trace[inside].max()) if inside.any() else floor
            chosen = sel is not None and abs(sel.freq - s.freq) < max(s.width, sel.width) / 2
            chosen_any = chosen_any or chosen
            bands.append(Band(lo, hi, GREEN if chosen else self.COLOR, 0.22 if chosen else 0.12, f"S{k}", owner="", edit=EDIT,
                              ylo=floor, yhi=peak + 3.0))
            info = [f"{fmt_hz(s.width)} wide"]
            if s.snr is not None:
                info.append(f"SNR {s.snr:.1f} dB")
            if s.duty is not None and s.duty < 0.9:
                info.append(f"{s.duty*100:.0f}% on")
            if chosen:
                info.append("analysed")
            rows.append([f"S{k} {fmt_hz(s.freq)}", ", ".join(info)])
        if sel is not None and not chosen_any: # set by hand to something the search did not find
            bands.append(Band(sel.freq - sel.width/2, sel.freq + sel.width/2, GREEN, 0.22, "sel", owner="", edit=EDIT))
            rows.append([fmt_hz(sel.freq), f"{fmt_hz(sel.width)} wide, analysed"])
        return Result(rows or [["-", "no signals"]], [], bands)
