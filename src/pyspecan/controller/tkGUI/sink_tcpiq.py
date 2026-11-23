"""Controller for the TCPIQ sink"""
from .sink import Sink


def rate_text(r: float) -> str:
    return f"{r / 1e6:.3f} MS/s" if r >= 1e6 else f"{r / 1e3:.3f} kS/s" if r >= 1e3 else f"{r:.1f} S/s"

class SinkTcpIq(Sink):
    def __init__(self, ctrl):
        super().__init__(ctrl)
        self.ctrl.view.sink.cl_btn_measured.config(command=lambda: self.ctrl.apply_setting("fs", "measured"))

    def draw_tb(self, status):
        """Who sends and the rate samples arrive at, every block"""
        st = status.get("stream")
        if st is None:
            return
        where = f"listening on {st['address']}" if st["listen"] else f"server {st['address']}"
        text = (f"From {st['peer']} ({where})" if st["peer"]
                else f"Waiting for a sender on {st['address']}" if st["listen"] else f"Waiting for {st['address']}")
        if st["measured"]:
            text += f", arriving at {rate_text(st['measured'])}"
            if st["mismatch"]:
                text += f", not the {rate_text(st['declared'])} declared"
        v = self.ctrl.view.sink
        v.cl_lbl_stream.config(text=text)
        v.cl_btn_measured.config(state="normal" if st["measured"] else "disabled")

    def draw_cl(self):
        self.draw_tb(self.ctrl.get_status())
