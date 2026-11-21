import atexit
import inspect
import os
import time

import pysdrlib
from pysdrlib import err as _err

from ...obj import Frequency
from .sink import Sink, SinkConfig

PROGRAM = "pyspecan" # what a pysdrlib server shows next to a radio this program holds
SERVERS_ENV = "PYSPECAN_SERVERS" # known pysdrlib servers, when --servers is not given
PROBE_TIMEOUT = 2.0 # [s] a known server has to answer in when looking for a radio, else it is skipped

def parse_servers(value=None) -> list[str]:
    """Known pysdrlib servers: a comma separated 'tcp://host:5555, tcp://other:5555' (or a list),
    None: the PYSPECAN_SERVERS environment variable. Each is checked to be an address, duplicates dropped"""
    if value is None:
        value = os.environ.get(SERVERS_ENV, "")
    parts = value if isinstance(value, (list, tuple)) else str(value).split(",")
    out = []
    for p in (str(p).strip() for p in parts):
        if not p:
            continue
        base, ident = SinkLive.split_address(p)
        if ident is not None:
            raise ValueError(f"a known server is an address without a radio, tcp://host:port, got {p!r}")
        if base not in out:
            out.append(base)
    return out

def _addresses(*groups) -> list[str]:
    """Server addresses (None, one, or lists of them), each once, in order"""
    out = []
    for g in groups:
        for a in ([g] if isinstance(g, str) else g or []):
            if a and a not in out:
                out.append(a)
    return out

def args_live(sink):
    sink.add_argument("-d", "--device", default=None, help="radio to use: a driver name (uhd), 'auto' or nothing for the first one found (see --list), or one on a pysdrlib server: tcp://host:5555 (the first it hosts), tcp://host:5555/<id> (hackrf-0), tcp://host:5555/<driver> (open a new one)")
    sink.add_argument("--serial", default=None, help="which unit of the driver, as --list shows")
    sink.add_argument("--no-dc-block", action="store_true", help="keep the DC spike at the center (radios with a direct-conversion receiver, like the HackRF, have one): by default the average of each block is removed")
    sink.add_argument("--claim", action="store_true", help="take control of a hosted remote radio that is free (tune it, start it), without it you only watch")
    sink.add_argument("--servers", default=None, help=f"known pysdrlib servers, comma separated tcp://host:5555: with no -d and no radio attached here the first usable one is picked, --list and the radio picker show theirs (default: ${SERVERS_ENV})")

class SinkLive(Sink):
    __slots__ = (
        "dev", "gain_frac", "claim", "remote", "hosted", "serial", "target", "server", "stalls", "lag", "skipped", "retuned",
        "inverted", "granted", "dc_block", "servers"
    )
    LAG_MIN = 0.1     # [s] of backlog that is dropped to catch up with the radio (or 3 blocks, if longer)
    STALLS = 3        # reads without samples in a row before the radio is called lost
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
        self.skipped = 0      # blocks dropped to catch up, or because they came from before a retune
        self.retuned = False  # the radio was tuned elsewhere and this sink followed
        self.inverted = False # the radio's spectrum comes mirrored (a converter with its LO above the signal): undone in next()
        self.granted = None   # what a server that chose the radio says it can do nearest to what was asked
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
                if self.remote and not self.controlling: # one we opened, closing it takes its control back
                    dev.claim()
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
        self.granted = None
        if ident is None:
            ident = pick_remote(address, self.claim)
            if ident is not None:
                print(f"using {ident} on {address}", flush=True)
        chooses, names = _connect_features()
        who = {"program": PROGRAM} if names else {} # an older pysdrlib does not take who we are
        if ident is None: # nothing hosted to use: the server chooses the radio to open, for what was asked
            try:
                if not chooses: # an older pysdrlib cannot choose: open the first type the server has
                    raise _err.NoDevice("attached: none")
                dev = pysdrlib.connect(address, **who, **self._wanted())
            except _err.NoDevice as e: # it chooses among the radios attached to it: with none attached, open the first type it has
                types = _server_radios(address)[1]
                if not types or "attached: none" not in str(e): # attached radios that do not fit are an answer
                    raise
                dev = pysdrlib.connect(address, types[0], **who)
            self.granted = getattr(dev, "granted", None)
            print(f"using {dev.id} on {address}" + self._granted_note(), flush=True)
        elif "@" in ident: # an attached radio the server has not opened yet: driver@serial
            driver, serial = ident.split("@", 1)
            dev = pysdrlib.connect(address, driver, serial=serial, **who)
        else:
            dev = pysdrlib.connect(address, ident, claim=self.claim, **who)
        self.remote = True
        # attaching to a hosted id gives the device with that id, naming a driver opens a new one (hackrf-N) that is ours to close
        self.hosted = getattr(dev, "id", None) == ident
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
        tried = []
        for address in self.servers:
            try:
                ident = pick_remote(address, self.claim, PROBE_TIMEOUT)
            except ImportError:
                raise
            except Exception as e: # down, busy, or hosting nothing it can open
                self.log.warning("skipping %s: %s", address, e)
                tried.append(f"{address} ({e})")
                continue
            return address if ident is None else f"{address}/{ident}"
        raise _err.NoDevice("no radios found on this machine, and none to use on the known servers: " + "; ".join(tried)
                            + " (--list shows what there is)")

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
        self.target = name
        self.stalls = self.skipped = 0
        self.lag = 0.0
        if name and "://" not in name and "@" in name: # driver@serial, as the radio list gives them
            name, self.serial = name.split("@", 1)
        if name in (None, "", "auto") and self.servers and not pysdrlib.find():
            name = self._pick_server()
        if name and "://" in name:
            self.server = self.split_address(name)[0]
            self.dev = self._connect_remote(name)
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
        """Read one block. The radio's own report (pysdrlib's RxMeta) decides what is shown: a block from before a
        retune, or one that sat in the queue while this program was busy, is dropped so the display tracks the radio"""
        fs = float(self._Fs.raw)
        timeout = max(2.0, 4*count/fs)
        for attempt in range(4):
            try:
                x, meta = self.dev.read(count, timeout=timeout, meta=True)
            except _err.Timeout:
                self.stalls += 1
                self.log.warning("no samples from the device")
                if self.stalls >= self.STALLS:
                    raise ConnectionError("the radio stopped delivering samples (use reconnect)") from None
                return False
            except _err.NotStreaming:
                if self.controlling:
                    raise
                if attempt == 0: # a viewer is told by the server, ask what it is doing now
                    self.dev.refresh()
                    if self.dev.state["rx"]:
                        continue
                raise RuntimeError("this radio is not receiving and you are only watching it, claim it to start it (--claim, or the Claim control)") from None
            self.stalls = 0
            last = attempt == 3
            if meta.freq != self._cf.raw or meta.rate != self._Fs.raw:
                if not self.controlling: # somebody else tuned it: follow
                    self._follow(meta.freq, meta.rate)
                    fs = float(self._Fs.raw)
                elif not last:           # stale, from before our own retune
                    self.skipped += 1
                    continue
            self.lag = max(0.0, time.monotonic() - meta.time - count/fs) if meta.time else 0.0
            if self.lag > max(self.LAG_MIN, 3*count/fs) and not last:
                self.skipped += 1
                self.dev.flush() # pysdrlib: drop the queue and read what is current
                continue
            if self.dc_block:
                x = x - x.mean() # the receiver's own DC offset is the spike at the center, a signal there is only its average
            self._samples = x.conj() if self.inverted else x # conjugating the IQ mirrors the spectrum back
            return True
        return True

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
        try:
            self.inverted = bool(self.dev.get_rx_inverted())
        except Exception: # a pysdrlib or server that predates chains: nothing is mirrored
            self.inverted = False

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
            "control": control, "device": self.name, "server": self.server, "id": getattr(self.dev, "id", None),
            "lag": round(self.lag, 3), "skipped": self.skipped,
            "can_claim": self.remote and not self.controlling, "inverted": self.inverted,
            "antennas": self.antennas(), "antenna": self.get_antenna(),
        }

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


def _connect_features() -> tuple[bool, bool]:
    """(pysdrlib.connect can pick the radio itself when given none, it takes `program`): older releases do neither"""
    try:
        chooses = inspect.signature(pysdrlib.connect).parameters["device"].default is not inspect.Parameter.empty
        from pysdrlib.remote.client import RemoteDevice
        return chooses, "program" in inspect.signature(RemoteDevice.__init__).parameters
    except Exception:
        return False, False

# --- antennas --- #
def describe_antenna(chain) -> str:
    """What is fitted on a chain as text: `ANT500 (Whip / monopole, length 20-88 cm, 50 ohm)`, '' when it names none"""
    if chain is None or not getattr(chain, "antenna", None):
        return ""
    info = chain.describe() or {"name": chain.antenna}
    try:
        from pysdrlib.remote.cli import format_antenna
        return format_antenna(info)
    except Exception: # the remote extra is not installed
        return str(info.get("name", chain.antenna))

def radio_antennas(dev, selected=None) -> list[dict]:
    """The receive antenna ports of a `pysdrlib.Device` (opened or not), with what is fitted on each: [{port, antenna, label,
    selected, inverted}]. `selected`: the port in use (default: ask the device)"""
    if dev is None:
        return []
    try:
        ports = list(dev.caps.antennas.get("rx", []))
        chains = [c for c in dev.caps.chains if c.direction == "rx"]
        if selected is None:
            selected = dev.get_rx_antenna()
    except Exception:
        return []
    out = []
    for port in ports or [None]:
        chain = next((c for c in chains if port is not None and c.port == port), None) or \
            next((c for c in chains if c.port is None), None) or (chains[0] if chains and not ports else None)
        if port is None and chain is None:
            continue
        text = describe_antenna(chain)
        name = port if port is not None else (chain.port or "")
        out.append({"port": name, "antenna": text, "selected": port is not None and port == selected,
                    "inverted": bool(chain and chain.invert),
                    "label": name + (f" - {text}" if text and name else text)})
    return out

# --- what radios there are --- #
def _server_radios(address: str, timeout: float = 5.0) -> tuple[list[dict], list[str]]:
    """(hosted radios, device types it can open) of a pysdrlib server"""
    try:
        from pysdrlib.remote import Client
    except ImportError as exc:
        raise ImportError("using a pysdrlib server needs pyzmq: pip install pysdrlib[remote]") from exc
    with Client(address, timeout) as client:
        return client.list(), client.types()

def _server_attached(address: str, timeout: float = 5.0) -> list[dict]:
    """The radios attached to a server's machine that it has not opened (older servers do not say: none)"""
    from pysdrlib.remote import Client
    with Client(address, timeout) as client:
        try:
            return [a for a in client.available() if not a.get("hosted")]
        except Exception:
            return []

def _attached_target(base: str, a: dict) -> str:
    return f"{base}/{a['driver']}" + (f"@{a['serial']}" if a.get("serial") else "")

def pick_remote(address: str, claim: bool = False, timeout: float = 5.0) -> str | None:
    """The radio to use on a server when none was named: with `claim` a hosted one nobody controls, to watch one that is
    already receiving (else any hosted one), and when it hosts nothing None: the server picks a new radio (ours) to open"""
    hosted, types = _server_radios(address, timeout)
    if claim:
        free = [d for d in hosted if not d["controlled"]]
        if free:
            return free[0]["id"]
        if hosted:
            raise _err.Busy(f"every radio on {address} has a controller: {', '.join(d['id'] for d in hosted)}")
    elif hosted:
        return next((d for d in hosted if d["state"]["rx"]), hosted[0])["id"]
    if types:
        return None # a new radio opened for us, chosen by the server
    raise _err.NoDevice(f"{address} hosts no radios and can open none")

def _local_ports(info) -> list[str]:
    """The receive antenna ports of an attached radio, from its driver's declared capabilities (it is not opened)"""
    try:
        return [a["label"] for a in radio_antennas(pysdrlib.device(info.driver), selected="")]
    except Exception:
        return []

def _hosted_chains(d: dict) -> list[str]:
    """What the server says sits between a hosted radio and the air: `rx RX2: ANT500 (...), LO 9750 MHz (inverted)`"""
    out = []
    for c in d.get("chains") or []:
        if c.get("direction") != "rx":
            continue
        text = ""
        if c.get("antenna"):
            try:
                from pysdrlib.remote.cli import format_antenna
                text = format_antenna(c["antenna"])
            except Exception:
                text = str(c["antenna"].get("name", ""))
        lo = f"LO {c['lo'] / 1e6:g} MHz{' (inverted)' if c.get('invert') else ''}" if c.get("lo") else ""
        out.append(" ".join(x for x in (f"{c['port']}:" if c.get("port") else "", text, lo) if x))
    return out

def list_devices(address: str | list[str] | None = None) -> list[str]:
    """Lines describing the radios pyspecan can use, with the -d that picks each: those attached here, and those of
    pysdrlib servers (`address`: one, or a list). A server that does not answer is listed as such"""
    lines = []
    found = pysdrlib.find()
    lines.append("attached to this machine:" if found else "attached to this machine: none")
    for info in found:
        pick = f"-s live -d {info.driver}" + (f" --serial {info.serial}" if info.serial else "")
        lines.append(f"  {info.label:<36} {pick}")
        for port in _local_ports(info):
            lines.append(f"      antenna {port}")
    addresses = _addresses(address)
    for addr in addresses:
        base, _ = SinkLive.split_address(addr)
        try:
            hosted, types = _server_radios(base, PROBE_TIMEOUT if len(addresses) > 1 else 5.0)
        except ImportError:
            raise
        except Exception as e:
            if len(addresses) == 1: # the one server asked about: say why
                raise
            lines.append(f"on the server {base}: not answering ({e})")
            continue
        lines.append(f"on the server {base}:" if hosted or types else f"on the server {base}: nothing")
        for d in hosted:
            state = ("receiving" if d["state"]["rx"] else "idle") + (", controlled" if d["controlled"] else ", free")
            lines.append(f"  {d['id']:<12} {d['name']:<14} {Frequency.get(d['cf'])} / {Frequency.get(d['Fs'])} {state:<22} -s live -d {base}/{d['id']}" + ("" if d["controlled"] else "  [--claim to control]"))
            for chain in _hosted_chains(d):
                lines.append(f"      antenna {chain}")
        attached = _server_attached(base)
        for a in attached:
            lines.append(f"  {a['driver']:<12} {a['label']:<28} attached, not open  -s live -d {_attached_target(base, a)}")
        if not attached: # a server that does not say what is attached: the types it can open
            for t in types:
                lines.append(f"  {t:<12} (opens a new one)  -s live -d {base}/{t}")
    if not addresses:
        lines.append(f"a pysdrlib server's radios: --list -d tcp://host:5555, or name servers with --servers / ${SERVERS_ENV}")
    return lines

def radio_choices(address: str | list[str] | None = None) -> list[dict]:
    """[{label, target}] for a device picker, `target` is what set_device takes. `address`: a server, or a list"""
    out = []
    for info in pysdrlib.find():
        out.append({"label": f"{info.label} (this machine)", "target": info.driver + (f"@{info.serial}" if info.serial else "")})
    for address in _addresses(address):
        try:
            hosted, types = _server_radios(address, PROBE_TIMEOUT)
        except Exception as e: # the picker must still work when a server is down
            out.append({"label": f"{address}: {e}", "target": None})
            continue
        for d in hosted:
            who = "receiving" if d["state"]["rx"] else "idle"
            out.append({"label": f"{d['id']} {d['name']} ({who}, {'controlled' if d['controlled'] else 'free'}) on {address}", "target": f"{address}/{d['id']}"})
        attached = _server_attached(address)
        out += [{"label": f"{a['label']} (attached, not open) on {address}", "target": _attached_target(address, a)} for a in attached]
        if not attached: # a server that does not say what is attached: the types it can open
            out += [{"label": f"open a new {t} on {address}", "target": f"{address}/{t}"} for t in types]
    return out
