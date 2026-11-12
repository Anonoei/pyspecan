import pysdrlib
from pysdrlib import err as _err

from ...utils import args
from .sink import Sink, args_sink, SinkConfig

from ...obj import Frequency

def args_live(parser):
    sink = args.get_group(parser, "Sink (LIVE)")
    args_sink(sink)
    sink.add_argument("-d", "--device", default=None, help="device type")

class SinkLive(Sink):
    __slots__ = (
        "dev", "gain_frac"
    )
    def __init__(self, model, **kwargs):
        self.dev: pysdrlib.Device = None # type: ignore
        device = kwargs.get("device", None)
        super().__init__(model, **kwargs)
        self.gain_frac = None # overall receive gain, a fraction 0-1 of the device range
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
            self.dev.set_rx_freq(cf)
            self.dev.set_rx_sample_rate(Fs)
            self._Fs = Frequency.get(self.dev.get_rx_sample_rate())
            self._cf = Frequency.get(self.dev.get_rx_freq())
            self.set_rx(None)
            self.dev.start_rx()

    def _set_fs(self, fs):
        return self.dev.set_rx_sample_rate(fs, flush=True)
    def _set_cf(self, cf):
        return self.dev.set_rx_freq(cf, flush=True)

    def next(self, count: int):
        try:
            self._samples = self.dev.read(count, timeout=max(2.0, 4*count/float(self._Fs.raw)))
        except _err.Timeout:
            self.log.warning("no samples from the device")
            return False
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
