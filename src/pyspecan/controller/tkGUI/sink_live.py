"""Controller for LIVE sink"""
import pysdrlib

from ...utils import args
from .sink import Sink, args_sink

def args_live(parser):
    sink = args.get_group(parser, "Sink (LIVE)")
    args_sink(sink)

class SinkLive(Sink):
    def __init__(self, ctrl):
        super().__init__(ctrl)

        self.ctrl.view.sink.cl_cb_dev.config(values=list([d for d in pysdrlib.devices.ls()]))
        self.ctrl.view.sink.cl_cb_dev.bind("<<ComboboxSelected>>", self.handle_event)

        self.ctrl.view.sink.cl_ent_rx.bind("<Return>", self.handle_event)
        self.build_stages()

    def draw_cl(self):
        self.ctrl.view.sink.cl_var_dev.set(str(type(self.ctrl.model.sink.dev).__name__))
        self.draw_gains()

    def build_stages(self):
        """(Re)build one gain entry per stage the device declares"""
        v = self.ctrl.view.sink
        for ent in v.set_stages(self.ctrl.model.sink.rx_stages()).values():
            ent.bind("<Return>", self.handle_event)
        self.draw_gains()

    def draw_gains(self):
        m = self.ctrl.model.sink
        v = self.ctrl.view.sink
        g = m.get_rx()
        v.cl_var_rx.set("" if g is None else f"{g:.2f}")
        for name, var in v.cl_stage_vars.items():
            var.set(str(m.get_rx_stage(name)))

    # --- GUI bind events and setters --- #
    def handle_event(self, event):
        if event.widget == self.ctrl.view.sink.cl_cb_dev:
            self.set_device(self.ctrl.view.sink.cl_var_dev.get())
        elif event.widget == self.ctrl.view.sink.cl_ent_rx:
            self.set_rx(self.ctrl.view.sink.cl_var_rx.get())
        else:
            for name, ent in self.ctrl.view.sink.cl_stage_ents.items():
                if event.widget == ent:
                    self.set_rx_stage(name, self.ctrl.view.sink.cl_stage_vars[name].get())
                    break

    def set_device(self, device):
        self.ctrl.model.sink.set_device(device)
        print(f"Device set to '{self.ctrl.model.sink.name}'")
        self.draw_cl()
        self.build_stages()

    def set_rx(self, gain):
        try:
            self.ctrl.model.sink.set_rx(float(gain))
        except (ValueError, pysdrlib.err.InvalidValue):
            pass
        self.draw_cl()

    def set_rx_stage(self, name, gain):
        try:
            self.ctrl.model.sink.set_rx_stage(name, float(gain))
        except (ValueError, pysdrlib.err.InvalidValue):
            pass
        self.draw_cl()
