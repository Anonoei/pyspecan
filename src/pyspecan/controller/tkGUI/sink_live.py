"""Controller for LIVE sink"""
import pysdrlib

from .sink import Sink

class SinkLive(Sink):
    def __init__(self, ctrl):
        super().__init__(ctrl)

        v = self.ctrl.view.sink
        self.choices: dict[str, str | None] = {} # label -> what set_device takes
        self.antennas: dict[str, str] = {} # label -> antenna port
        self.list_radios()
        v.cl_cb_dev.bind("<<ComboboxSelected>>", self.handle_event)
        v.cl_cb_dev.bind("<Return>", self.handle_event) # a typed address, tcp://host:5555/id
        v.cl_cb_ant.bind("<<ComboboxSelected>>", self.handle_event)
        v.cl_btn_claim.config(command=self.toggle_control)
        v.cl_btn_reconnect.config(command=lambda: self.ctrl.run_command("reconnect"))

        self.ctrl.view.sink.cl_ent_rx.bind("<Return>", self.handle_event)
        self.ctrl.view.sink.cl_ent_rx.bind("<FocusOut>", self.handle_event)
        self.build_stages()

    def list_radios(self):
        try:
            radios = self.ctrl.radios()
        except Exception as e: # a server that is down must not stop the window opening
            self.log.warning("listing radios: %s", e)
            radios = []
        self.choices = {r["label"]: r["target"] for r in radios if r["target"]}
        self.ctrl.view.sink.cl_cb_dev.config(values=list(self.choices))

    def draw_cl(self):
        v = self.ctrl.view
        radio = self.ctrl.sink.status() or {}
        control = radio.get("control", "local")
        label = {"local": "Radio on this machine", "controlling": "Controlling", "watching": "Watching (controlled elsewhere)"}[control]
        extra = f" - {radio['lag']*1000:.0f} ms behind" if radio.get("lag", 0) > 0.1 else ""
        v.sink.cl_lbl_status.config(text=f"{label}: {radio.get('device', '')}{extra}")
        if radio.get("inverted"):
            v.sink.cl_lbl_status.config(text=v.sink.cl_lbl_status.cget("text") + " (spectrum mirrored, corrected)")
        v.sink.cl_var_dev.set(radio.get("device", ""))
        ants = radio.get("antennas", [])
        self.antennas = {a["label"]: a["port"] for a in ants}
        v.sink.set_antennas(list(self.antennas), next((a["label"] for a in ants if a["selected"]), None))
        v.sink.cl_cb_ant.config(state="disabled" if control == "watching" else "readonly")
        v.sink.cl_btn_claim.config(text="Release" if control == "controlling" else "Claim",
                                   state="normal" if control != "local" else "disabled")
        tunable = "disabled" if control == "watching" else "normal" # it can only be looked at, not told what to do
        for w in (v.cl_ent_fs, v.cl_ent_cf, v.sink.cl_ent_rx, *v.sink.cl_stage_ents.values()):
            w.config(state=tunable)
        self.draw_gains()

    def toggle_control(self):
        control = (self.ctrl.sink.status() or {}).get("control")
        self.ctrl.run_command("release" if control == "controlling" else "claim")
        self.build_stages()

    def build_stages(self):
        """(Re)build one gain entry per stage the device declares"""
        v = self.ctrl.view.sink
        for ent in v.set_stages(self.ctrl.model.sink.rx_stages()).values():
            ent.bind("<Return>", self.handle_event)
            ent.bind("<FocusOut>", self.handle_event)
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
        elif event.widget == self.ctrl.view.sink.cl_cb_ant:
            self.set_antenna(self.ctrl.view.sink.cl_var_ant.get())
        elif event.widget == self.ctrl.view.sink.cl_ent_rx:
            self.set_rx(self.ctrl.view.sink.cl_var_rx.get())
        else:
            for name, ent in self.ctrl.view.sink.cl_stage_ents.items():
                if event.widget == ent:
                    self.set_rx_stage(name, self.ctrl.view.sink.cl_stage_vars[name].get())
                    break

    def set_device(self, device):
        target = self.choices.get(device, device) # a listed label, or a typed target
        self.ctrl.apply_setting("device", target)
        self.list_radios()
        self.build_stages()

    def set_antenna(self, label):
        self.ctrl.apply_setting("antenna", self.antennas.get(label, label)) # shows what the radio refuses
        self.draw_cl()

    def _failed(self, e):
        """Say why a gain was not applied (it is easy to type dB in the 0-1 entry), the next draw replaces it"""
        self.log.warning("gain: %s", e)
        self.ctrl.view.sink.cl_lbl_status.config(text=f"Gain not set: {e}")

    def set_rx(self, gain):
        try:
            self.ctrl.model.sink.set_rx(float(gain))
        except Exception as e:
            self.draw_cl()
            return self._failed(e)
        self.draw_cl()

    def set_rx_stage(self, name, gain):
        try:
            self.ctrl.model.sink.set_rx_stage(name, float(gain))
        except Exception as e:
            self.draw_cl()
            return self._failed(e)
        self.draw_cl()
