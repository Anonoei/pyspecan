import atexit
import os
import re
import time

import pysdrlib
from pysdrlib import err as _err
from pysdrlib import targets as _targets
from pysdrlib.base.antennas import format_antenna

from ...obj import Frequency
from .sink import Sink, SinkConfig

PROGRAM = "pyspecan" # what a pysdrlib server shows next to a radio this program holds
SERVERS_ENV = "PYSPECAN_SERVERS" # known pysdrlib servers when --servers is not given (else pysdrlib's PYSDRLIB_SERVERS)
PROBE_TIMEOUT = 2.0 # [s] a known server has to answer in when looking for a radio, else it is skipped

def parse_servers(value=None) -> list[str]:
    """Known pysdrlib servers as endpoints: 'radiohost, tcp://other:5556' (commas or whitespace, or a list); None:
    $PYSPECAN_SERVERS, else $PYSDRLIB_SERVERS. An entry naming a radio is refused, duplicates are dropped"""
    if value is None:
        value = os.environ.get(SERVERS_ENV) or os.environ.get(_targets.SERVERS_ENV, "")
    parts = value if isinstance(value, (list, tuple)) else re.split(r"[,\s]+", str(value))
    out = []
    for part in (str(x).strip().rstrip("/") for x in parts):
        if not part:
            continue
        rest = part.split("://", 1)[1] if "://" in part else part
        if "@" in rest or ("/" in rest and not part.startswith("ipc://")):
            raise ValueError(f"a known server is an address without a radio (radiohost, host:port, tcp://host:port), got {part!r}")
        server = _targets.endpoint(part)
        if server not in out:
            out.append(server)
    return out

def remote_target(name):
    """The pysdrlib Target of `name` when it names a server ([server/]device, see pysdrlib.targets), else None"""
    if not name or name == "auto":
        return None
    t = _targets.parse_target(name)
    return t if t.server is not None else None

def _addresses(*groups) -> list[str]:
    """Server endpoints (None, one, or lists of them), each once, in order"""
    out = []
    for g in groups:
        for a in ([g] if isinstance(g, str) else g or []):
            if a and _targets.endpoint(a) not in out:
                out.append(_targets.endpoint(a))
    return out

def args_live(sink):
    sink.add_argument("-d", "--device", default=None, help="radio to use, as --list shows: a driver (uhd, hackrf@<serial>), 'auto' or nothing for the first one found, or one on a pysdrlib server: radiohost (it picks), radiohost/hackrf-0 (one it hosts), radiohost/hackrf (open a new one), radiohost:5556/hackrf@<serial> (one attached to it); tcp://host:port works too")
    sink.add_argument("--serial", default=None, help="which unit of the driver, as --list shows")
    sink.add_argument("--no-dc-block", action="store_true", help="keep the DC spike at the center (radios with a direct-conversion receiver, like the HackRF, have one): by default the average of each block is removed")
    sink.add_argument("--claim", action="store_true", help="take control of a hosted remote radio that is free (tune it, start it), without it you only watch")
    sink.add_argument("--servers", default=None, help=f"known pysdrlib servers, comma separated (radiohost, host:5556, tcp://host:port): with no -d and no radio attached here the first usable one is picked, --list and the radio picker show theirs (default: ${SERVERS_ENV}, else $PYSDRLIB_SERVERS)")

class SinkLive(Sink):
    __slots__ = (
        "dev", "gain_frac", "claim", "remote", "hosted", "serial", "target", "server", "stalls", "lag", "skipped", "retuned",
        "inverted", "granted", "dc_block", "servers", "dropped", "hw_time", "recorder", "record_error", "_next_index"
    )
    STALLS = 3        # reads without samples in a row before the radio is called lost
    RECORD_READ_S = 1.0 # [s] most samples read at once while recording (what is queued beyond waits for the next read)
    def __init__(self, model, **kwargs):
        self.dev: pysdrlib.Device = None # type: ignore
        device = kwargs.get("device", None)
        super().__init__(model, **kwargs)
        self.gain_frac = None # overall receive gain, a fraction 0-1 of the device range
        self.serial = kwargs.get("serial", None)
        self.dc_block = not kwargs.get("no_dc_block", False) # remove the DC offset of the receiver from each block
        self.claim = bool(kwargs.get("claim", False)) # remote: take control of a free hosted radio
        self.servers = parse_servers(kwargs.get("servers")) # known pysdrlib servers, looked at when no radio is attached here
        self.remote = False   # the device is on a pysdrlib server
        self.hosted = False   # ... and was already hosted there, so closing only detaches from it
        self.target = None    # what was asked for (-d), to reconnect to
        self.server = None    # address of the pysdrlib server in use, to list its radios
        self.stalls = 0       # reads in a row that got no samples
        self.lag = 0.0        # [s] how far behind the radio the last block was
        self.skipped = 0      # samples skipped to show the newest (queued while busy, or from before a retune)
        self.retuned = False  # the radio was tuned elsewhere and this sink followed
        self.inverted = False # the radio's spectrum comes mirrored (a converter with its LO above the signal): undone in next()
        self.granted = None   # what a server that chose the radio says it can do nearest to what was asked
        self.dropped = 0      # samples the radio lost (overflows), as pysdrlib reports them
        self.hw_time = None   # the radio's own clock at the last block's first sample, for radios that keep one
        self.recorder = None  # pysdrlib FileSink while recording
        self.record_error = "" # why the last recording stopped by itself
        self._next_index = None # stream index after the last block shown, to tell whether the next one follows it
        self.set_device(device) # type: ignore

    def show(self, ind=2):
        print(" "*ind + f"{type(self.dev).__name__}")

    def ready(self):
        return self.dev is not None

    @property
    def name(self):
        return f"{type(self.dev).__name__}"
    @property
    def id(self):
        return None

    @property
    def controlling(self) -> bool:
        """Can this program tune and start the device (always for a local one)"""
        return self.dev.is_controller if self.dev is not None else not self.remote

    def close(self):
        """Let go of the device. A radio a server already hosted is detached from, so it stays open there for others"""
        self.stop_record()
        dev, self.dev = self.dev, None # type: ignore
        if dev is None:
            return
        try:
            if self.remote and self.hosted:
                dev.detach() # gives up control, which stops what this program started
            else:
                if self.remote and not self.controlling: # one we opened, closing it takes its control back
                    dev.claim()
                if dev.state["rx"] and self.controlling:
                    dev.stop_rx()
                dev.close()
        except Exception as e: # the server may be gone, there is nothing left to release
            self.log.warning("closing the device: %s", e)

    def _connect_remote(self, target):
        """A radio on a pysdrlib server, from its pysdrlib Target"""
        address, device, serial = target.server, target.device, target.serial
        where = _targets.short(address)
        self.granted = None
        if device is None:
            device = pick_remote(address, self.claim)
            if device is not None:
                print(f"using {device} on {where}", flush=True)
        who = {"program": PROGRAM}
        if device is None: # nothing hosted to use: the server chooses the radio to open, for what was asked
            try:
                dev = pysdrlib.connect(address, **who, **self._wanted())
            except _err.NoDevice as e: # it chooses among the radios attached to it: with none attached, open the first type it has
                types = [r.driver for r in _discover([address], local=False, raise_errors=True) if r.state == "openable"]
                if not types or e.reason != "none_attached": # attached radios that do not fit are an answer
                    raise
                dev = pysdrlib.connect(address, types[0], **who)
            self.granted = dev.granted
            print(f"using {dev.id} on {where}" + self._granted_note(), flush=True)
        else: # hosted (attach), a driver (open a new one), or driver@serial (one attached to it)
            dev = pysdrlib.open(_targets.format_target(address, device, serial), program=PROGRAM,
                                **({} if serial else {"claim": self.claim}))
        self.remote = True
        # attaching to a hosted id gives the device with that id, naming a driver opens a new one (hackrf-N) that is ours to close
        self.hosted = dev.id == device and not serial
        atexit.register(self.close)
        return dev

    def _granted_note(self) -> str:
        g = self.granted or {}
        bits = []
        if g.get("antenna"):
            bits.append(f"antenna {g['antenna']}")
        if g.get("inverted"):
            bits.append("spectrum mirrored, corrected")
        return f" ({', '.join(bits)})" if bits else ""

    def _wanted(self) -> dict:
        """The need/want a server picks a radio by: what was asked for is a need, the defaults only a wish"""
        need = {}
        if int(self._cf.raw) != int(SinkConfig.cf):
            need["freq"] = self._cf.raw
        if int(self._Fs.raw) != int(SinkConfig.Fs):
            need["rate"] = self._Fs.raw
        return {"need": need, "want": {"freq": self._cf.raw, "rate": self._Fs.raw}}

    def _pick_server(self) -> str:
        """No radio attached here: the first known server with one to use, as a -d target. Servers that do not
        answer, or have nothing usable (every radio controlled, with --claim), are skipped"""
        errors = []
        found = _discover(self.servers, local=False, timeout=PROBE_TIMEOUT, errors=errors)
        down = dict(errors)
        tried = []
        for address in self.servers:
            if address in down:
                tried.append(f"{_targets.short(address)} ({down[address]})")
                continue
            try:
                device = _choose([r for r in found if r.server == address], address, self.claim)
            except Exception as e: # busy, or hosting nothing it can open
                self.log.warning("skipping %s: %s", address, e)
                tried.append(f"{_targets.short(address)} ({e})")
                continue
            return _targets.format_target(address, device)
        raise _err.NoDevice("no radios found on this machine, and none to use on the known servers: " + "; ".join(tried)
                            + " (--list shows what there is)")

    def _open_local(self, name: str | None):
        """An opened radio attached to this machine: a driver by name, or the first one found"""
        if name in (None, "", "auto"):
            found = pysdrlib.find()
            if not found:
                raise _err.NoDevice("no radios found on this machine, name a driver with -d, or a server with -d radiohost (--list shows what there is)")
            info = found[0]
            print(f"using {info.label}" + (f" ({len(found) - 1} more, see --list)" if len(found) > 1 else ""), flush=True)
            return info.open()
        return pysdrlib.open(name, serial=self.serial) if self.serial else pysdrlib.open(name)

    def set_device(self, name: str):
        self.log.debug("set_device(%s)", name)
        self.close()
        self.remote = self.hosted = False
        self.target = name
        self.stalls = self.skipped = self.dropped = 0
        self.lag = 0.0
        self._next_index = self.hw_time = None
        if name in (None, "", "auto") and self.servers and not pysdrlib.find():
            name = self._pick_server()
        target = remote_target(name)
        if target is not None:
            self.server = target.server
            self.dev = self._connect_remote(target)
            if self.controlling:
                if int(self._cf.raw) != int(SinkConfig.cf): # only what was asked for, a hosted radio keeps its gain
                    self.dev.set_rx_freq(self._cf.raw)
                if int(self._Fs.raw) != int(SinkConfig.Fs):
                    self.dev.set_rx_sample_rate(self._Fs.raw)
            self._Fs = Frequency.get(self.dev.get_rx_sample_rate())
            self._cf = Frequency.get(self.dev.get_rx_freq())
            self.gain_frac = self.dev.get_rx_gain()
            self._read_inverted()
            if self.controlling and not self.dev.state["rx"]:
                self.dev.start_rx()
            elif not self.controlling:
                self.log.warning("watching %s: it is controlled elsewhere (or nobody), use --claim to take it", name)
            return
        self.dev = self._open_local(name)
        cf = None if int(self._cf.raw) == int(SinkConfig.cf) else self._cf.raw
        Fs = None if int(self._Fs.raw) == int(SinkConfig.Fs) else self._Fs.raw
        self.dev.set_rx_freq(cf)
        self.dev.set_rx_sample_rate(Fs)
        self._Fs = Frequency.get(self.dev.get_rx_sample_rate())
        self._cf = Frequency.get(self.dev.get_rx_freq())
        self._read_inverted()
        self.set_rx(None)
        self.dev.start_rx()

    def _need_control(self):
        if not self.controlling:
            raise ValueError("this radio is controlled elsewhere, claim it to tune it (--claim, or the Claim control, when it is free)")

    def _set_fs(self, fs):
        self._need_control()
        return self.dev.set_rx_sample_rate(fs, flush=True)
    def _set_cf(self, cf):
        self._need_control()
        got = self.dev.set_rx_freq(cf, flush=True)
        self._read_inverted() # the chain that applies can depend on where it is tuned
        return got

    def next(self, count: int):
        """Read one block: the newest `count` samples at the radio's current settings (pysdrlib's read(latest=True)
        skips what queued up while this program was busy, and what came before a retune). While recording, everything
        queued is read (and written) instead, and the display shows the newest `count` of it"""
        fs = float(self._Fs.raw)
        timeout = max(2.0, 4*count/fs)
        for attempt in range(4):
            recording = self.recorder is not None
            n = max(count, min(self.dev.wait_available(0), int(self.RECORD_READ_S * fs))) if recording else count
            try:
                x, meta = self.dev.read(n, timeout=timeout, meta=True, latest=not recording)
            except _err.Lost as e: # unplugged, failing, or its server is gone
                raise ConnectionError(f"the radio is gone: {e} (use reconnect)") from None
            except _err.Timeout:
                self.stalls += 1
                self.log.warning("no samples from the device")
                if self.stalls >= self.STALLS:
                    raise ConnectionError("the radio stopped delivering samples (use reconnect)") from None
                return False
            except _err.NotStreaming:
                if self.controlling:
                    raise
                raise RuntimeError("this radio is not receiving and you are only watching it, claim it to start it (--claim, or the Claim control)") from None
            self.stalls = 0
            self.dropped += meta.dropped
            self.skipped += meta.discarded
            if self.inverted:
                x = x.conj() # conjugating the IQ mirrors the spectrum back (a recording is stored the right way round)
            if recording:
                self._record(x, meta)
            if meta.freq != self._cf.raw or meta.rate != self._Fs.raw:
                if not self.controlling: # somebody else tuned it: follow
                    self._follow(meta.freq, meta.rate)
                    fs = float(self._Fs.raw)
                elif recording and attempt < 3: # read whole, so from before our own retune: recorded, not shown
                    continue
            self.lag = max(0.0, time.monotonic() - meta.time - n/fs) if meta.time else 0.0
            shown = n - count # the newest `count` are shown
            x = x[shown:]
            # the stream index counts lost samples too: a block follows the last one shown when it starts where that
            # ended (meta.next_index), with nothing lost inside it
            start = meta.index + shown + sum(k for at, k in meta.gaps if 0 < at <= shown)
            self.contiguous = start == self._next_index and not any(at > shown for at, _ in meta.gaps)
            self._next_index = meta.next_index
            self.hw_time = meta.hw_time
            self.block_index = start
            self.block_time = None if meta.wall_time is None else meta.wall_time + shown / fs
            if self.dc_block:
                x = x - x.mean() # the receiver's own DC offset is the spike at the center, a signal there is only its average
            self._samples = x
            return True
        return True

    # --- recording --- #
    def start_record(self, path) -> str:
        """Write every sample received from now on to `path`: a SigMF recording (format cf32) unless its extension names
        a format (.cfile, .cs16, .cu8...). Returns the path of the samples"""
        from pysdrlib import FileSink, Formats
        if self.recorder is not None:
            raise ValueError(f"already recording to {self.recorder.path}")
        path = str(path)
        sigmf = Formats.from_extension(path) is None # no format in its name: SigMF says what it is
        sink = FileSink(path, sigmf=sigmf, scale=True, clip=True, rate=self._Fs.raw, freq=self._cf.raw,
                        hw=self.dev.id or self.name)
        sink.open()
        self.recorder, self.record_error = sink, ""
        self._next_index = None # what was queued is read whole: the display starts over
        return str(sink.path)

    def stop_record(self):
        """Close the recording (its SigMF metadata is written)"""
        rec, self.recorder = self.recorder, None
        if rec is not None:
            rec.close()

    def _record(self, x, meta):
        try:
            self.recorder.write(x, meta=meta)
        except Exception as e: # a full disk must not stop the display: the recording ends, and says why
            self.record_error = f"recording stopped: {type(e).__name__}: {e}"
            self.log.error(self.record_error)
            try:
                self.stop_record()
            except Exception:
                self.recorder = None

    def recording(self) -> dict | None:
        """{path, seconds} of the recording in progress, None when not recording"""
        rec = self.recorder
        if rec is None:
            return None
        return {"path": str(rec.path), "seconds": round(rec.count / float(self._Fs.raw), 3)}

    # --- sweeping --- #
    def sweep(self, freqs, count: int):
        """Tune to each of `freqs` in turn and take `count` samples there, each received after the retune settled:
        [(frequency, samples)], mirrored and DC offset corrected as blocks are. The radio is tuned back after"""
        self._need_control()
        if self.recorder is not None:
            raise ValueError("not while recording: a sweep retunes the radio")
        out = []
        timeout = max(2.0, 4*count/float(self._Fs.raw))
        try:
            for freq, x, meta in self.dev.sweep(list(freqs), count=int(count), timeout=timeout, meta=True, on_drop="retry"):
                if self.dev.get_rx_inverted(): # the chain in use can depend on where it is tuned
                    x = x.conj()
                if self.dc_block:
                    x = x - x.mean()
                self.dropped += meta.dropped
                out.append((float(freq), x))
        finally:
            self.dev.set_rx_freq(self._cf.raw, flush=True)
            self._next_index = None # the blocks after it are not those before
        return out

    def _follow(self, freq, rate):
        """A radio controlled elsewhere changed: show what it is now"""
        self._cf, self._Fs = Frequency.get(freq), Frequency.get(rate)
        self._read_inverted()
        self.retuned = True

    def take_retuned(self) -> bool:
        """Did the radio change under this sink since last asked (the plots then start over)"""
        r, self.retuned = self.retuned, False
        return r

    def _read_inverted(self):
        """Does the radio's spectrum come mirrored (an LNB or converter with its LO above the signal, see pysdrlib's `Chain`)"""
        self.inverted = bool(self.dev.get_rx_inverted())

    # --- antennas --- #
    def antennas(self) -> list[dict]:
        """The receive antenna ports the radio has: [{port, antenna, label, selected, inverted}]. `antenna` says what is fitted
        on the port when the operator described it (pysdrlib server --frontends), [] when the radio has just the one"""
        return radio_antennas(self.dev)
    def get_antenna(self):
        return self._call_dev("get_rx_antenna")
    def set_antenna(self, port):
        """Select the receive antenna port. A chain with another converter retunes the radio over the air"""
        self._need_control()
        self.log.debug("set_rx_antenna(%s)", port)
        self.dev.set_rx_antenna(port)
        self._cf = Frequency.get(self.dev.get_rx_freq())
        self._read_inverted()
    def _call_dev(self, name):
        try:
            return getattr(self.dev, name)()
        except Exception:
            return None

    # --- who controls the radio --- #
    def claim_control(self):
        """Take control of a hosted radio that is free: tune it, start it"""
        if not self.remote:
            raise ValueError("a radio attached here is always yours")
        if self.controlling:
            return
        self.dev.claim() # pysdrlib raises Busy when somebody has it
        self.dev.refresh()
        if not self.dev.state["rx"]:
            self.dev.start_rx()
        self._sync()
    def release_control(self):
        """Give the radio up (it stops receiving), and keep watching"""
        if not self.remote or not self.controlling:
            raise ValueError("you are not controlling a hosted radio")
        self.dev.release()
        self.dev.refresh()

    def _sync(self):
        self._Fs = Frequency.get(self.dev.get_rx_sample_rate())
        self._cf = Frequency.get(self.dev.get_rx_freq())
        self.gain_frac = self.dev.get_rx_gain()
        self._read_inverted()
        self.retuned = True

    def reconnect(self):
        """Connect again to what was asked for at the start or last chosen (a server that went away and came back)"""
        self.set_device(self.target)

    def status(self) -> dict:
        """What the views show about the radio"""
        control = "local" if not self.remote else ("controlling" if self.controlling else "watching")
        return {
            "control": control, "device": self.name, "server": self.server, "id": self.dev.id if self.dev is not None else None,
            **self.live_status(),
            "can_claim": self.remote and not self.controlling, "inverted": self.inverted,
            "antennas": self.antennas(), "antenna": self.get_antenna(),
        }

    def live_status(self) -> dict:
        """What changes block to block: how far behind, samples lost (by the radio) and skipped (to show the newest), the radio's
        clock at the last block (radios that keep one), the recording"""
        return {"lag": round(self.lag, 3), "skipped": self.skipped, "dropped": self.dropped, "hw_time": self.hw_time,
                "recording": self.recording(), "record_error": self.record_error}

    def radios(self) -> list[dict]:
        """Radios that can be chosen: [{label, target}], those attached here and the server's"""
        return radio_choices(_addresses(self.server, self.servers))

    def set_rx(self, gain):
        """Set the overall receive gain, a fraction of the device's range 0-1 (None: the defaults)"""
        self.log.debug("set_rx_gain(%s)", gain)
        self.gain_frac = self.dev.set_rx_gain(gain)
    def get_rx(self):
        return self.gain_frac

    # --- device-specific gain stages, decibels, named as the device declares them --- #
    def rx_stages(self):
        """{stage name: GainStage(min, max, step, default)}"""
        return self.dev.rx_gain_stages()
    def set_rx_stage(self, name, gain):
        self.log.debug("set_rx_stage(%s, %s)", name, gain)
        gain = self.dev.set_rx_gain_db(gain, stage=name)
        self.gain_frac = self.dev.get_rx_gain()
        return gain
    def get_rx_stage(self, name):
        return self.dev.get_rx_gain_db(name)

    def start_rx(self):
        self.log.debug("start_rx()")
        self.dev.start_rx()
    def stop_rx(self):
        self.log.debug("stop_rx()")
        self.dev.stop_rx()


# --- antennas --- #
def radio_antennas(dev) -> list[dict]:
    """The receive antenna ports of an open `pysdrlib.Device` with what is fitted on each (its rx_antenna_info):
    [{port, antenna, label, selected, inverted}], [] for a lone port with nothing said about it"""
    if dev is None:
        return []
    try:
        info = dev.rx_antenna_info()
    except Exception:
        return []
    out = []
    for a in info:
        port = a["port"] or ""
        text = format_antenna(a["antenna"]) if a["antenna"] else ""
        if not port and not text and not a["inverted"]:
            continue
        out.append({"port": port, "antenna": text, "selected": bool(port) and bool(a["selected"]), "inverted": a["inverted"],
                    "label": port + (f" - {text}" if text and port else text)})
    return out

# --- what radios there are --- #
def _discover(servers, local=True, timeout=5.0, errors=None, raise_errors=False) -> list:
    """pysdrlib.discover over these servers (endpoints). errors: a list that gets (server, exception) for each that did
    not answer; raise_errors: raise the first instead"""
    errs = [] if errors is None else errors
    try:
        found = pysdrlib.discover(servers=list(servers), local=local, timeout=timeout, errors=errs)
    except ImportError as exc:
        raise ImportError("using a pysdrlib server needs pyzmq: pip install pysdrlib[remote]") from exc
    if raise_errors and errs:
        raise errs[0][1]
    return found

def _choose(radios, address: str, claim: bool) -> str | None:
    """The device to use among what a server has (Radios): with `claim` a hosted one nobody controls, to watch one that
    is receiving (else any hosted one); None when it hosts nothing: the server picks a new radio (ours) to open"""
    hosted = [r for r in radios if r.state == "hosted"]
    if claim:
        free = [r for r in hosted if not r.controlled]
        if free:
            return free[0].id
        if hosted:
            raise _err.Busy(f"every radio on {_targets.short(address)} has a controller: {', '.join(r.id for r in hosted)}")
    elif hosted:
        return next((r for r in hosted if r.receiving), hosted[0]).id
    if radios:
        return None # a new radio opened for us, chosen by the server
    raise _err.NoDevice(f"{_targets.short(address)} hosts no radios and can open none")

def pick_remote(address: str, claim: bool = False, timeout: float = 5.0) -> str | None:
    """The radio to use on a server when none was named (see _choose)"""
    address = _targets.endpoint(address)
    return _choose(_discover([address], local=False, timeout=timeout, raise_errors=True), address, claim)

def _antenna_text(a: dict) -> str:
    """One of a Radio's antennas ({port, name, antenna}) as text: `RX2: ANT500 (Whip / monopole, ...)`"""
    info = a.get("antenna")
    text = format_antenna(info) if info else (a.get("name") or "")
    return " ".join(x for x in (f"{a['port']}:" if a.get("port") else "", text) if x)

def _state_text(r) -> str:
    return ("receiving" if r.receiving else "idle") + (", controlled" if r.controlled else ", free")

def list_devices(address: str | list[str] | None = None) -> list[str]:
    """Lines describing the radios pyspecan can use, with the -d that picks each: those attached here, and those of
    pysdrlib servers (`address`: one, or a list). A server that does not answer is listed as such"""
    addresses = _addresses(address)
    errors = []
    found = _discover(addresses, local=True, timeout=PROBE_TIMEOUT if len(addresses) > 1 else 5.0, errors=errors)
    if len(addresses) == 1 and errors: # the one server asked about: say why
        raise errors[0][1]
    down = dict(errors)
    here = [r for r in found if r.server is None]
    lines = ["attached to this machine:" if here else "attached to this machine: none"]
    for r in here:
        lines.append(f"  {r.label:<36} -s live -d {r.target}")
        lines += [f"      antenna {_antenna_text(a)}" for a in r.antennas]
    for addr in addresses:
        where = _targets.short(addr)
        if addr in down:
            lines.append(f"on the server {where}: not answering ({down[addr]})")
            continue
        radios = [r for r in found if r.server == addr]
        lines.append(f"on the server {where}:" if radios else f"on the server {where}: nothing")
        for r in radios:
            if r.state == "hosted":
                tuned = f"{Frequency.get(r.extra.get('cf', 0))} / {Frequency.get(r.extra.get('Fs', 0))}"
                lines.append(f"  {r.id:<12} {r.driver:<14} {tuned} {_state_text(r):<22} -s live -d {r.target}"
                             + ("" if r.controlled else "  [--claim to control]"))
                lines += [f"      antenna {_antenna_text(a)}" for a in r.antennas]
            elif r.state == "attached":
                lines.append(f"  {r.driver:<12} {r.label:<28} attached, not open  -s live -d {r.target}")
            else:
                lines.append(f"  {r.driver:<12} (opens a new one)  -s live -d {r.target}")
    if not addresses:
        lines.append(f"a pysdrlib server's radios: --list -d radiohost, or name servers with --servers / ${SERVERS_ENV} / ${_targets.SERVERS_ENV}")
    return lines

def radio_choices(address: str | list[str] | None = None) -> list[dict]:
    """[{label, target}] for a device picker, `target` is what set_device takes. `address`: a server, or a list. A server
    that is down is listed with why, and no target"""
    addresses = _addresses(address)
    errors = []
    found = _discover(addresses, local=True, timeout=PROBE_TIMEOUT, errors=errors)
    out = []
    for r in found:
        where = "this machine" if r.server is None else _targets.short(r.server)
        if r.server is None:
            label = f"{r.label} (this machine)"
        elif r.state == "hosted":
            label = f"{r.id} {r.driver} ({_state_text(r)}) on {where}"
        elif r.state == "attached":
            label = f"{r.label} (attached, not open)"
        else:
            label = f"open a new {r.driver} on {where}"
        out.append({"label": label, "target": r.target})
    out += [{"label": f"{_targets.short(s)}: {e}", "target": None} for s, e in errors]
    return out
