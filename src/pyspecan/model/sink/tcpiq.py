"""TCP IQ stream, as a client of a sample server or a server that a sender connects to (pysdrlib's tcpiq)"""
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
    __slots__ = ("dev", "timeout")
    def __init__(self, model, **kwargs):
        super().__init__(model, **kwargs)
        self.timeout = float(kwargs.get("tcp_timeout", 1.0))
        host = kwargs.get("tcp_host", None)
        port = int(kwargs.get("tcp_port", 1234))
        listen = bool(kwargs.get("tcp_listen", False))
        fmt = kwargs.get("tcp_fmt") or "cf32"

        self.dev: pysdrlib.Device = pysdrlib.open("tcpiq", host=host, port=port, listen=listen, sample_format=fmt)
        # the stream's rate and frequency can't be set from here, they're what we say it is
        cf = None if int(self._cf.raw) == int(SinkConfig.cf) else self._cf.raw
        Fs = None if int(self._Fs.raw) == int(SinkConfig.Fs) else self._Fs.raw
        self.dev.initialize(cf=cf, Fs=Fs)
        self._Fs = Frequency.get(self.dev.get_rx_sample_rate())
        self._cf = Frequency.get(self.dev.get_rx_freq())
        self.dev.start_rx()

    def show(self, ind=2):
        print(" "*ind + f"TCP IQ {self.dev.peer or 'waiting for peer'} [{self.dev.SAMPLE_FORMAT}]")

    def ready(self):
        return self.dev is not None

    @property
    def name(self):
        return "tcpiq"

    MISMATCH = 0.1 # measured this far off the declared rate (as pysdrlib warns): say so

    def measured_rate(self) -> float | None:
        """Samples per second arriving over the last second or so (pysdrlib), None until known. Only a sender paced in
        real time arrives at its sample rate (nc replaying a file arrives at network speed): it is shown, never applied"""
        return self.dev.measured_rate

    def stream_status(self) -> dict:
        rate, fs = self.measured_rate(), float(self._Fs.raw)
        return {"peer": self.dev.peer, "measured": rate, "declared": fs,
                "mismatch": rate is not None and abs(rate / fs - 1) > self.MISMATCH}

    def _set_fs(self, fs):
        return self.dev.set_rx_sample_rate(fs)
    def _set_cf(self, cf):
        return self.dev.set_rx_freq(cf)

    def next(self, count: int):
        from .live import block_time
        try:
            x, meta = self.dev.read(count, timeout=self.timeout, meta=True)
        except _err.Timeout:
            return False
        except _err.Lost as e: # the server closed the stream, or stopped answering
            raise ConnectionError(f"the TCP IQ stream is gone: {e}") from None
        self.contiguous = self.block_index is not None and meta.index == self.block_index + count and not meta.gaps
        self.block_index, self.block_time = meta.index, block_time(meta)
        self._samples = np.asarray(x)
        return True

    def close(self):
        if self.dev is not None and self.dev.state["open"]:
            if self.dev.state["rx"]:
                self.dev.stop_rx()
            self.dev.close()
