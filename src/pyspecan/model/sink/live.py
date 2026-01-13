import pysdrlib

from ...utils import args
from .sink import Sink, args_sink, SinkConfig

from ...obj import Frequency

def args_live(parser):
    sink = args.get_group(parser, "Sink (LIVE)")
    args_sink(sink)
    sink.add_argument("-d", "--device", default=None, help="device type")

class SinkLive(Sink):
    __slots__ = (
        "dev", "gain"
    )
    def __init__(self, model, **kwargs):
        self.dev: pysdrlib.Device = None # type: ignore
        device = kwargs.get("device", None)
        super().__init__(model, **kwargs)
        self.gain = {
            "rf": None,
            "if": None,
            "bb": None
        }
        self.set_device(device) # type: ignore

    def show(self, ind=2):
        print(" "*ind + f"{type(self.dev).__name__}")

    @property
    def name(self):
        return f"{type(self.dev).__name__}"
    @property
    def id(self):
        return None

    def set_device(self, name: str):
        self.log.debug("set_device(%s)", name)
        if self.dev is not None:
            if self.dev.state["rx"]:
                self.dev.stop_rx()
            self.dev.close()

        sdr = pysdrlib.devices.get(name)
        if sdr is not None:
            self.dev = sdr.Device()
            self.dev.open()

            cf = None if int(self._cf.raw) == int(SinkConfig.cf) else self._cf.raw
            Fs = None if int(self._Fs.raw) == int(SinkConfig.Fs) else self._Fs.raw
            # self.dev.initialize(cf=cf, Fs=Fs)
            self.dev.set_freq(cf)
            self.dev.set_sample_rate(Fs)
            self._Fs = Frequency.get(self.dev.get_sample_rate())
            self._cf = Frequency.get(self.dev.get_freq())
            self.set_rx(None)
            self.dev.start_rx()

    def _set_fs(self, fs):
        return self.dev.set_sample_rate(fs)
    def _set_cf(self, cf):
        return self.dev.set_freq(cf)

    def next(self, count: int):
        # self.log.debug("next(%s)", count)
        self._samples = self.dev.get_samples()[-count:]
        return True

    def set_rx(self, gain):
        self.log.debug("set_rx_gain(%s)", gain)
        gain = self.dev.set_rx_gain(gain)
        if gain.get("rf", None) is not None:
            self.gain["rf"] = gain["rf"]
        if gain.get("if", None) is not None:
            self.gain["if"] = gain["if"]
        if gain.get("bb", None) is not None:
            self.gain["bb"] = gain["bb"]
    def set_rx_rf(self, gain):
        self.log.debug("set_rx_rf(%s)", gain)
        self.gain["rf"] = self.dev.set_rx_rf_gain(gain)
    def set_rx_if(self, gain):
        self.log.debug("set_rx_if(%s)", gain)
        self.gain["if"] = self.dev.set_rx_if_gain(gain)
    def set_rx_bb(self, gain):
        self.log.debug("set_rx_bb(%s)", gain)
        self.gain["bb"] = self.dev.set_rx_bb_gain(gain)

    def get_rx_rf(self):
        return self.gain["rf"]
    def get_rx_if(self):
        return self.gain["if"]
    def get_rx_bb(self):
        return self.gain["bb"]

    def has_rx_rf(self):
        return self.dev.CONFIG.GAIN_RX_RF
    def has_rx_if(self):
        return self.dev.CONFIG.GAIN_RX_IF
    def has_rx_bb(self):
        return self.dev.CONFIG.GAIN_RX_BB

    def start_rx(self):
        self.log.debug("start_rx()")
        self.dev.start_rx()
    def stop_rx(self):
        self.log.debug("stop_rx()")
        self.dev.stop_rx()
