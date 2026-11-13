import atexit

import pysdrlib
from pysdrlib import err as _err

from ...utils import args
from .sink import Sink, args_sink, SinkConfig

from ...obj import Frequency

def args_live(parser):
    sink = args.get_group(parser, "Sink (LIVE)")
    args_sink(sink)
    sink.add_argument("-d", "--device", default=None, help="radio to use: a driver name (uhd), 'auto' or nothing for the first one found (see --list), or one on a pysdrlib server: tcp://host:5555 (the first it hosts), tcp://host:5555/<id> (hackrf-0), tcp://host:5555/<driver> (open a new one)")
    sink.add_argument("--serial", default=None, help="which unit of the driver, as --list shows")
    sink.add_argument("--claim", action="store_true", help="take control of a hosted remote radio that is free (tune it, start it), without it you only watch")

class SinkLive(Sink):
    __slots__ = (
        "dev", "gain_frac", "claim", "remote", "hosted", "serial"
    )
    def __init__(self, model, **kwargs):
        self.dev: pysdrlib.Device = None # type: ignore
        device = kwargs.get("device", None)
        super().__init__(model, **kwargs)
        self.gain_frac = None # overall receive gain, a fraction 0-1 of the device range
        self.serial = kwargs.get("serial", None)
        self.claim = bool(kwargs.get("claim", False)) # remote: take control of a free hosted radio
        self.remote = False   # the device is on a pysdrlib server
        self.hosted = False   # ... and was already hosted there, so closing only detaches from it
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
        return not self.remote or bool(getattr(self.dev, "is_controller", False))

    def close(self):
        """Let go of the device. A radio a server already hosted is detached from, so it stays open there for others"""
        dev, self.dev = self.dev, None # type: ignore
        if dev is None:
            return
        try:
            if self.remote and self.hosted:
                dev.detach() # gives up control, which stops what this program started
            else:
                if dev.state["rx"] and self.controlling:
                    dev.stop_rx()
                dev.close()
        except Exception as e: # the server may be gone, there is nothing left to release
            self.log.warning("closing the device: %s", e)

    @staticmethod
    def split_address(name: str) -> tuple[str, str | None]:
        """'tcp://host:5555/hackrf-0' -> ('tcp://host:5555', 'hackrf-0'), 'tcp://host:5555' -> ('tcp://host:5555', None)"""
        scheme, sep, rest = name.partition("://")
        host, _, ident = rest.partition("/")
        if not sep or not scheme or not host or "/" in ident:
            raise ValueError(f"expected tcp://host:port[/<device id or driver>], got {name!r}")
        return f"{scheme}://{host}", (ident or None)

    def _connect_remote(self, name: str):
        address, ident = self.split_address(name)
        if ident is None:
            ident = pick_remote(address, self.claim)
            print(f"using {ident} on {address}", flush=True)
        dev = pysdrlib.connect(address, ident, claim=self.claim)
        self.remote = True
        # attaching to a hosted id gives the device with that id, naming a driver opens a new one (hackrf-N) that is ours to close
        self.hosted = getattr(dev, "id", None) == ident
        atexit.register(self.close)
        return dev

    def _open_local(self, name: str | None):
        """An opened radio attached to this machine: a driver by name, or the first one found"""
        if name in (None, "", "auto"):
            found = pysdrlib.find()
            if not found:
                raise _err.NoDevice("no radios found on this machine, name a driver with -d, or a server with -d tcp://host:5555 (--list shows what there is)")
            info = found[0]
            print(f"using {info.label}" + (f" ({len(found) - 1} more, see --list)" if len(found) > 1 else ""), flush=True)
            return info.open()
        return pysdrlib.open(name, serial=self.serial) if self.serial else pysdrlib.open(name)

    def set_device(self, name: str):
        self.log.debug("set_device(%s)", name)
        self.close()
        self.remote = self.hosted = False
        if name and "://" in name:
            self.dev = self._connect_remote(name)
            if self.controlling:
                if int(self._cf.raw) != int(SinkConfig.cf): # only what was asked for, a hosted radio keeps its gain
                    self.dev.set_rx_freq(self._cf.raw)
                if int(self._Fs.raw) != int(SinkConfig.Fs):
                    self.dev.set_rx_sample_rate(self._Fs.raw)
            self._Fs = Frequency.get(self.dev.get_rx_sample_rate())
            self._cf = Frequency.get(self.dev.get_rx_freq())
            self.gain_frac = self.dev.get_rx_gain()
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
        self.set_rx(None)
        self.dev.start_rx()

    def _need_control(self):
        if not self.controlling:
            raise ValueError("this radio is controlled elsewhere, relaunch with --claim to tune it (when it is free)")

    def _set_fs(self, fs):
        self._need_control()
        return self.dev.set_rx_sample_rate(fs, flush=True)
    def _set_cf(self, cf):
        self._need_control()
        return self.dev.set_rx_freq(cf, flush=True)

    def next(self, count: int):
        try:
            self._samples = self.dev.read(count, timeout=max(2.0, 4*count/float(self._Fs.raw)))
        except _err.Timeout:
            self.log.warning("no samples from the device")
            return False
        except _err.NotStreaming:
            if self.controlling:
                raise
            raise RuntimeError("this radio is not receiving and you are only watching it, relaunch with --claim to start it") from None
        return True

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


# --- what radios there are --- #
def _server_radios(address: str) -> tuple[list[dict], list[str]]:
    """(hosted radios, device types it can open) of a pysdrlib server"""
    try:
        from pysdrlib.remote import Client
    except ImportError as exc:
        raise ImportError("using a pysdrlib server needs pyzmq: pip install pysdrlib[remote]") from exc
    with Client(address, 5.0) as client:
        return client.list(), client.types()

def pick_remote(address: str, claim: bool = False) -> str:
    """The radio to use on a server when none was named: with `claim` a hosted one nobody controls, to watch one that is
    already receiving (else any hosted one), and when it hosts nothing the first type it can open (a new radio, ours)"""
    hosted, types = _server_radios(address)
    if claim:
        free = [d for d in hosted if not d["controlled"]]
        if free:
            return free[0]["id"]
        if hosted:
            raise _err.Busy(f"every radio on {address} has a controller: {', '.join(d['id'] for d in hosted)}")
    elif hosted:
        return next((d for d in hosted if d["state"]["rx"]), hosted[0])["id"]
    if types:
        return types[0] # a new radio opened for us
    raise _err.NoDevice(f"{address} hosts no radios and can open none")

def list_devices(address: str | None = None) -> list[str]:
    """Lines describing the radios pyspecan can use, with the -d that picks each: those attached here, and a pysdrlib server's"""
    lines = []
    found = pysdrlib.find()
    lines.append("attached to this machine:" if found else "attached to this machine: none")
    for info in found:
        pick = f"-s live -d {info.driver}" + (f" --serial {info.serial}" if info.serial else "")
        lines.append(f"  {info.label:<36} {pick}")
    if address:
        base, ident = SinkLive.split_address(address)
        hosted, types = _server_radios(base)
        lines.append(f"on the server {base}:" if hosted or types else f"on the server {base}: nothing")
        for d in hosted:
            state = ("receiving" if d["state"]["rx"] else "idle") + (", controlled" if d["controlled"] else ", free")
            lines.append(f"  {d['id']:<12} {d['name']:<14} {Frequency.get(d['cf'])} / {Frequency.get(d['Fs'])} {state:<22} -s live -d {base}/{d['id']}" + ("" if d["controlled"] else "  [--claim to control]"))
        for t in types:
            lines.append(f"  {t:<12} (opens a new one)  -s live -d {base}/{t}")
    else:
        lines.append("a pysdrlib server's radios: --list -d tcp://host:5555")
    return lines
