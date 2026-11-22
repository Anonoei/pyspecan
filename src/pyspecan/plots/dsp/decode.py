"""Decode: a signal through one of rpps' profiles (rp.profile.Decoder), its messages listed as they come"""
import datetime as dt
from collections import deque

import numpy as np

from ..base import About, Plot, plot
from ..frame import GREEN, LINE, RED, Axis, Frame, Table, TableRow, Trace
from ..freq import fmt_hz, freq_text, hz
from ..settings import Setting
from .analyzer import analyzer

HISTORY = 200 # blocks the message counts are drawn over
EPOCH_PLAUSIBLE = 946684800.0 # 2000-01-01: a time later than this is a date, earlier is seconds into a file

_CATALOGUE: list = []

def catalogue() -> list:
    """rpps' profiles (rp.profile.catalogue), read once: they don't change while pyspecan runs"""
    if not _CATALOGUE:
        from rpps.profile import catalogue as read
        _CATALOGUE.extend(read())
    return _CATALOGUE

def _profile(value) -> str:
    """coerce: a profile rpps has (blank: none, the table lists them)"""
    name = str(value).strip()
    if name:
        names = [p.name for p in catalogue()]
        if name not in names:
            raise ValueError(f"no profile {name!r}: one of {', '.join(names)}")
    return name

def _kinds(value) -> str:
    return ", ".join(k.strip() for k in str(value).split(",") if k.strip())

def when(t: float | None) -> str:
    """A message's time: UTC time of day for a date, seconds for a time into a file"""
    if t is None:
        return ""
    if t > EPOCH_PLAUSIBLE:
        return dt.datetime.fromtimestamp(t, dt.timezone.utc).strftime("%H:%M:%S.%f")
    return f"{t:.6f} s"

def fields_text(fields: dict, most: int = 8) -> str:
    items = [f"{k}={v}" for k, v in fields.items()]
    return ", ".join(items[:most]) + (", ..." if len(items) > most else "")

@plot("Decode")
class Decode(Plot):
    """A signal decoded by one of rpps' profiles (ADS-B, BLE advertising, AX.25, DVB-S/S2, CCSDS, LTE / NR to SIB1...):
    its messages as a table, newest first, and how many each block gave. Blank profile: the profiles, and which the
    sample rate can run"""
    TITLE = "Decode"
    CATEGORY = "Decoding"
    FEATURES = frozenset({LINE})
    ABOUT = About(
        data='The samples at the channel (the center frequency, the one given, or the analysed signal) shifted to 0 Hz, '
             "resampled to the profile's rate and run through it block by block (rpps.profile.Decoder); a short gap "
             "between blocks is filled, a longer one starts the profile's stream over",
        shows='The messages: time, kind, check, the framing fields and the payload (hex), newest first; the good and '
              'failed messages each block gave; the decoder state (measuring, searching, locked, lost) and its load',
        use=('Read ADS-B, BLE advertising, AX.25, DVB-S/S2 or CCSDS frames off the air or a capture',
             'Check an LTE or NR cell to its MIB and SIB1', 'See whether a link decodes, and how often a check fails'),
        # decoding ax25/afsk1200 (dev/benchmark.py's choice); other profiles cost what their decoding does, which the
        # "Load" readout says (LTE / NR to SIB1 near real time on their own). No profile costs nothing
        cost=7, # (its work comes in bursts: the median runs 5-10)
    )
    SETTINGS = (
        Setting("profile", "Profile", "text", default="", coerce=_profile, hint="none: list them", reset=True,
                group="Decode", help="the rpps profile to decode with (adsb/mode_s, ble/adv, lte/downlink...)"),
        Setting("channel", "Channel", "text", default="", coerce=freq_text, hint="center", reset=True, group="Decode",
                help="the signal's frequency, blank for the center frequency"),
        Setting("follow", "Follow selection", "check", default=False, reset=True, group="Decode",
                help="decode the signal the DSP plots analyse (the Analysis settings, or a box clicked) instead"),
        Setting("baud", "Symbol rate", "text", default="", coerce=freq_text, hint="profile's", reset=True, group="Decode",
                help="for a profile that leaves it open (DVB-S/S2, CCSDS): blank measures it on the selected signal"),
        Setting("kinds", "Kinds", "text", default="", coerce=_kinds, hint="all", reset=True, group="Decode",
                help="the message kinds wanted, comma separated (pbch, pdsch...): the steps the others need do not run"),
        Setting("failed", "Show failed", "check", default=False, group="Display",
                help="list messages whose check failed (live ADS-B gives many)"),
        Setting("rows", "Rows", "int", default=50, min=1, max=1000, group="Display", help="latest messages listed"),
        Setting("fill", "Gap fill", "number", default=0.05, min=0.0, step=0.01, reset=True, group="Decode", advanced=True,
                help="seconds: a gap between blocks this short is filled with zeros so the profile keeps its lock"),
    )

    def reset(self):
        self.close()
        self._key = None
        self._error = ""
        self.msgs: deque = deque(maxlen=1000)
        self.counts: deque = deque(maxlen=HISTORY) # (good, failed) per block

    def close(self):
        dec = getattr(self, "_dec", None)
        self._dec = None
        if dec is not None:
            try:
                self.msgs.extend(dec.close())
            except Exception:
                pass

    def _channel(self) -> tuple[float, float | None, str]:
        """(offset from the center, the channel's width or None, what it is for the readout)"""
        cf = self.source.cf
        if self.follow:
            sel = analyzer(self.source).selection(self.dsp_freq, self.dsp_bw) # type: ignore
            if sel is None:
                raise LookupError("no signal selected")
            return sel.freq - cf, sel.width, f"{fmt_hz(sel.freq)}, {fmt_hz(sel.width)} (selection)"
        f = hz(self.channel, cf)
        return f - cf, None, fmt_hz(f)

    def decoder(self, offset: float, bw):
        """The Decoder for these settings, a new one when they (or the source's tuning) changed"""
        from rpps.profile import Decoder
        fs, cf = self.source.fs, self.source.cf
        baud = hz(self.baud, 0.0) if self.baud else None
        kinds = [k.strip() for k in self.kinds.split(",") if k.strip()] or None
        key = (self.profile, baud, tuple(kinds or ()), round(offset, 1), bw, fs, cf, self.fill, self.source.epoch)
        if key != self._key:
            self.close()
            self._key = key
            self._dec = Decoder(self.profile, fs, offset=offset, cf=cf, baud=baud, bw=bw, fill=self.fill, kinds=kinds)
        return self._dec

    def render(self):
        if not self.profile:
            return self.catalogue()
        x = np.asarray(self.source.samples)
        if not len(x):
            return None
        good = failed = 0
        where = ""
        try:
            offset, bw, where = self._channel()
            dec = self.decoder(offset, bw)
            new = dec.feed(x, start=self.source.index, time=self.source.time)
            self.msgs.extend(new)
            good = sum(1 for m in new if m.crc_ok is not False)
            failed = len(new) - good
            self._error = ""
        except Exception as e: # a rate too low for the profile, a kind it does not give, nothing selected...
            self._error = f"{type(e).__name__}: {e}" if not isinstance(e, (ValueError, LookupError)) else str(e)
            self._key, self._dec = None, None
        self.counts.append((good, failed))
        return self.frame(where)

    def frame(self, where: str) -> Frame:
        counts = np.asarray(self.counts, dtype=float).reshape(-1, 2)
        k = np.arange(len(counts), dtype=float) - (len(counts) - 1)
        top = max(1.0, float(counts.max()) if len(counts) else 1.0) * 1.2
        ax = Axis(xmin=-(HISTORY - 1.0), xmax=0.0, ymin=0.0, ymax=top, xlabel="Blocks ago", ylabel="Messages",
                  traces=[Trace(counts[:, 0], k, color=GREEN, name="good"), Trace(counts[:, 1], k, color=RED, name="failed")]
                  if len(counts) else [])
        readout = [("Profile", self.profile)]
        if where:
            readout.append(("Channel", where))
        if self._error:
            readout.append(("Decode", self._error))
        elif self._dec is not None:
            st = self._dec.status
            state = st.get("state", "")
            readout.append(("State", f"{state}: {st['why']}" if st.get("why") else state))
            readout.append(("Messages", f"{st.get('good', 0)} good, {st.get('failed', 0)} failed"))
            if st.get("baud"):
                readout.append(("Rate", fmt_hz(st["baud"]).replace("Hz", "Bd")))
            if st.get("load") is not None:
                load = st["load"]
                readout.append(("Load", f"{load:.0%}" + (" - can't keep up" if load > 1 else "")))
        shown = [m for m in reversed(self.msgs) if self.failed or m.crc_ok is not False][:self.rows]
        rows = [TableRow(str(i), [when(m.time), m.kind, {True: "ok", False: "FAIL", None: "-"}[m.crc_ok],
                                   fields_text(m.fields or {}), (m.payload.hex() if m.payload else "")[:64]])
                for i, m in enumerate(shown)]
        return Frame([ax], title=self.TITLE, readout=readout, table=Table(["Time", "Kind", "Check", "Fields", "Payload"], rows))

    def catalogue(self) -> Frame:
        """No profile: what there is, and whether this sample rate can run each"""
        fs = self.source.fs
        rows = []
        for p in catalogue():
            req = p.requires
            if req.get("bw") is None:
                fits = "give its symbol rate (or follow a selection)"
            elif req["bw"] <= fs:
                fits = "yes"
            else:
                fits = f"needs {fmt_hz(req['bw'])} of span"
            rows.append(TableRow(p.name, [p.name, fits, (p.comment or "").split(". ")[0][:80]]))
        return Frame([Axis(xmin=-(HISTORY - 1.0), xmax=0.0, ymin=0.0, ymax=1.0, xlabel="Blocks ago", ylabel="Messages")],
                     title=self.TITLE, readout=[("Profile", "none: choose one in the settings")],
                     table=Table(["Profile", f"At {fmt_hz(fs).replace('Hz', 'S/s')}", "What"], rows))
