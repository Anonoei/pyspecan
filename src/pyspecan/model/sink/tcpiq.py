"""TCP IQ stream, as a client of a sample server or a server that a sender connects to (pysdrlib's tcpiq)

The sink logs where it listens or connects, and (on a thread of its own, playing or not) every sender that connects,
drops or takes over, what arrives, and a rate that disagrees with the declared one"""
import threading

import numpy as np
import pysdrlib
import pysdrlib.tcpiq
from pysdrlib import err as _err

from ...obj import Frequency
from .sink import Sink, SinkConfig


def args_tcpiq(sink):
    sink.add_argument("--tcp_host", default=None, help="client: server to connect to; server: address to listen on (default: all interfaces)")
    sink.add_argument("--tcp_port", default=1234, type=int, help="TCP port")
    sink.add_argument("--tcp_listen", action="store_true", help="be the server and wait for a sender to connect")
    sink.add_argument("--tcp_timeout", default=1.0, type=float, help="seconds to wait for a block of samples")
    sink.add_argument("--tcp_fmt", default="cf32", choices=pysdrlib.tcpiq.FORMATS,
                      help="what the sender sends: cf32 (two float32, GNU Radio), ci16 (two int16), cu8 (RTL-SDR)... (default: cf32)")

class SinkTcpIq(Sink):
    __slots__ = ("dev", "timeout", "_prev", "listen", "address", "_watch", "_stop")
    WATCH = 0.5          # [s] how often the watcher looks at the connection
    MISMATCH_POLLS = 6   # a rate off for this many looks in a row (about 3 s) is logged, once per sender
    def __init__(self, model, **kwargs):
        super().__init__(model, **kwargs)
        self.timeout = float(kwargs.get("tcp_timeout", 1.0))
        self._prev = None # the last block's RxMeta, to tell whether the next follows it
        host = kwargs.get("tcp_host", None)
        port = int(kwargs.get("tcp_port", 1234))
        listen = bool(kwargs.get("tcp_listen", False))
        fmt = kwargs.get("tcp_fmt") or "cf32"

        self.listen = listen
        self._watch: threading.Thread | None = None
        self._stop = threading.Event()
        where = f"{host or '0.0.0.0'}:{port}"
        if not listen: # connecting can take a while (timeout)
            self.log.info("TCP IQ: connecting to %s ...", where)
        try:
            self.dev: pysdrlib.Device = pysdrlib.open("tcpiq", host=host, port=port, listen=listen, sample_format=fmt)
        except Exception as e:
            self.log.error("TCP IQ: %s %s failed: %s", "listening on" if listen else "connecting to", where, e)
            raise
        # the port actually bound (listening on port 0 picks one)
        self.address = f"{host or '0.0.0.0'}:{self.dev.port if listen and self.dev.port else port}"
        # the stream's rate and frequency can't be set from here, they're what we say it is
        cf = None if int(self._cf.raw) == int(SinkConfig.cf) else self._cf.raw
        Fs = None if int(self._Fs.raw) == int(SinkConfig.Fs) else self._Fs.raw
        self.dev.initialize(cf=cf, Fs=Fs)
        self._Fs = Frequency.get(self.dev.get_rx_sample_rate())
        self._cf = Frequency.get(self.dev.get_rx_freq())
        self.dev.start_rx()
        self.log.info("TCP IQ: %s, %s, Fs %s S/s (declared), cf %sHz", self.describe(), self.dev.SAMPLE_FORMAT,
                      f"{float(self._Fs.raw):,.0f}", self._cf)
        self._watch = threading.Thread(target=self._watcher, name="tcpiq-watch", daemon=True)
        self._watch.start()

    def describe(self) -> str:
        """Where the stream comes from: 'listening on 0.0.0.0:1234 (every interface)', 'connected to host:port'"""
        if not self.listen:
            return f"connected to {self.address}"
        every = self.address.startswith(("0.0.0.0:", "[::]:", ":::"))
        return f"listening on {self.address}" + (" (every interface)" if every else "")

    def show(self, ind=2):
        print(" "*ind + f"TCP IQ {self.describe()}, {f'sender {self.dev.peer}' if self.dev.peer else 'waiting for a sender'} [{self.dev.SAMPLE_FORMAT}]")

    def _watcher(self):
        """Log what happens to the connection, whether anything is reading or not"""
        dev, log = self.dev, self.log
        peer, conns, replaced, rtl, rated, off, warned = None, 0, 0, False, False, 0, False
        while not self._stop.wait(self.WATCH):
            try:
                if not dev.state["open"]:
                    return
                now, n, r = dev.peer, dev.connections, dev.reconnects
                if r > replaced and now:
                    log.info("TCP IQ: sender %s took over from %s", now, peer or "the previous one")
                elif now != peer or n != conns:
                    if peer and not now:
                        log.warning("TCP IQ: sender %s dropped%s", peer,
                                    ", waiting for one to connect" if self.listen else "")
                    if now:
                        log.info("TCP IQ: sender %s %s", now, "connected" if self.listen else "is the server")
                if now != peer or n != conns: # judge the new sender afresh
                    rtl, rated, off, warned = False, False, 0, False
                peer, conns, replaced = now, n, r
                if not self.listen and dev.eof:
                    log.warning("TCP IQ: the server %s closed the stream", self.address)
                    return
                if now and not rtl and dev.rtl_tcp:
                    rtl = True
                    log.info("TCP IQ: rtl_tcp server, tuner %s", dev.rtl_tcp["tuner"])
                rate = dev.measured_rate
                if now and rate and not rated:
                    rated = True
                    log.info("TCP IQ: samples arriving at %s S/s", f"{rate:,.0f}")
                off = off + 1 if dev.rate_mismatch else 0
                if off >= self.MISMATCH_POLLS and not warned:
                    warned = True
                    log.warning("TCP IQ: samples arrive at %s S/s, but Fs is declared as %s S/s (set fs to `measured` "
                                "to use it; a sender replaying a file arrives faster)", f"{rate or 0:,.0f}",
                                f"{float(self._Fs.raw):,.0f}")
            except Exception as e: # never let the watcher take anything down
                log.debug("TCP IQ watcher: %s", e)

    def ready(self):
        return self.dev is not None

    @property
    def name(self):
        return "tcpiq"

    def measured_rate(self) -> float | None:
        """Samples per second arriving over the last second or so (pysdrlib), None until known. Only a sender paced in
        real time arrives at its sample rate (nc replaying a file arrives at network speed): it is shown, never applied"""
        return self.dev.measured_rate

    def stream_status(self) -> dict:
        return {"peer": self.dev.peer, "address": self.address, "listen": self.listen, "measured": self.measured_rate(), "declared": float(self._Fs.raw),
                "mismatch": bool(self.dev.rate_mismatch)}

    def _set_fs(self, fs):
        return self.dev.set_rx_sample_rate(fs)
    def _set_cf(self, cf):
        return self.dev.set_rx_freq(cf)

    def next(self, count: int):
        try:
            x, meta = self.dev.read(count, timeout=self.timeout, meta=True)
        except _err.Timeout:
            self.log.debug("TCP IQ: nothing within %g s (%s)", self.timeout,
                           f"sender {self.dev.peer}" if self.dev.peer else "no sender")
            return False
        except _err.Lost as e: # the server closed the stream, or stopped answering
            raise ConnectionError(f"the TCP IQ stream is gone: {e}") from None
        self.contiguous = self._prev is not None and meta.follows(self._prev) and not meta.gaps
        self._prev = meta
        self.block_index, self.block_time = meta.index, meta.wall_time
        self._samples = np.asarray(x)
        return True

    def close(self):
        self._stop.set()
        if self.dev is not None and self.dev.state["open"]:
            self.log.info("TCP IQ: closing (%s)", self.describe())
            if self.dev.state["rx"]:
                self.dev.stop_rx()
            self.dev.close()
