"""TCP IQ stream, as a client of a sample server or a server that a sender connects to (pysdrlib's tcpiq)"""
import numpy as np
import pysdrlib

from ...utils import args
from .sink import Sink, args_sink, SinkConfig

from ...obj import Frequency

def args_tcpiq(parser):
    sink = args.get_group(parser, "Sink (TCPIQ)")
    args_sink(sink)
    sink.add_argument("--host", default=None, help="client: server to connect to; server: address to listen on (default: all interfaces)")
    sink.add_argument("--port", default=1234, type=int, help="TCP port")
    sink.add_argument("--listen", action="store_true", help="be the server and wait for a sender to connect")
    sink.add_argument("--timeout", default=1.0, type=float, help="seconds to wait for a block of samples")

class SinkTcpIq(Sink):
    __slots__ = ("dev", "timeout")
    def __init__(self, model, **kwargs):
        super().__init__(model, **kwargs)
        self.timeout = float(kwargs.get("timeout", 1.0))
        host = kwargs.get("host", None)
        port = int(kwargs.get("port", 1234))
        listen = bool(kwargs.get("listen", False))

        self.dev: pysdrlib.Device = pysdrlib.open("tcpiq", host=host, port=port, listen=listen)
        # the stream's rate and frequency can't be set from here, they're what we say it is
        cf = None if int(self._cf.raw) == int(SinkConfig.cf) else self._cf.raw
        Fs = None if int(self._Fs.raw) == int(SinkConfig.Fs) else self._Fs.raw
        self.dev.initialize(cf=cf, Fs=Fs)
        self._Fs = Frequency.get(self.dev.get_rx_sample_rate())
        self._cf = Frequency.get(self.dev.get_rx_freq())
        self.dev.start_rx()

    def show(self, ind=2):
        print(" "*ind + f"TCP IQ {self.dev.peer or 'waiting for peer'}")

    def ready(self):
        return self.dev is not None

    @property
    def name(self):
        return "tcpiq"

    def _set_fs(self, fs):
        return self.dev.set_rx_sample_rate(fs)
    def _set_cf(self, cf):
        return self.dev.set_rx_freq(cf)

    def next(self, count: int):
        try:
            self._samples = np.asarray(self.dev.read(count, timeout=self.timeout))
        except TimeoutError:
            return False
        return True

    def close(self):
        if self.dev is not None and self.dev.state["open"]:
            if self.dev.state["rx"]:
                self.dev.stop_rx()
            self.dev.close()
