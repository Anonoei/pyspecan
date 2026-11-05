"""Controller for FILE sink"""
import argparse

from ...utils import args
from .sink import Sink, args_sink

from ...utils import dialog
from ...utils.time import strfmt_td
from ...model.sink.file import Format

import datetime as dt

def args_file(parser: argparse.ArgumentParser):
    sink = args.get_group(parser, "Sink (FILE)")
    args_sink(sink)

class SinkFile(Sink):
    def __init__(self, ctrl):
        super().__init__(ctrl)
        v = self.ctrl.view.sink
        self._updating = False # the slider follows playback, only user moves are seeks
        v.tb_sld_samp.scale.config(from_=0, to=self.ctrl.model.sink.max_samp, command=self.handle_sld_samp)

        v.tb_btn_prev.config(command=lambda: self.ctrl.run_command("prev"))
        v.tb_btn_next.config(command=lambda: self.ctrl.run_command("next"))

        v.cl_btn_file.config(command=self.handle_btn_file)
        v.cl_cb_file_fmt.config(values=Format.choices())
        v.cl_cb_file_fmt.bind("<<ComboboxSelected>>", self.handle_event)

    def draw_tb(self, status):
        v = self.ctrl.view.sink
        sink = self.ctrl.model.sink
        self._updating = True
        try:
            v.tb_var_samp.set(status.get("cur_samp", sink.cur_samp))
        finally:
            self._updating = False
        v.tb_var_time_cur.set(status.get("time_cur", strfmt_td(dt.timedelta(seconds=sink.cur_time()))))
        v.tb_var_time_tot.set(strfmt_td(dt.timedelta(seconds=sink.tot_time())))

    def draw_cl(self):
        v = self.ctrl.view.sink
        sink = self.ctrl.model.sink
        v.cl_var_file.set(str(sink.get_path()))
        v.cl_var_file_fmt.set(sink.get_fmt().name)
        v.tb_sld_samp.scale.config(to=sink.max_samp)

    # --- GUI bind events and setters --- #
    def handle_event(self, event):
        v = self.ctrl.view.sink
        if event.widget == v.cl_cb_file_fmt:
            self.ctrl.apply_setting("fmt", v.cl_var_file_fmt.get())

    def handle_btn_file(self):
        path = dialog.get_file(False)
        if path is not None:
            self.ctrl.apply_setting("path", str(path))

    def handle_sld_samp(self, *args):
        if self._updating:
            return
        self.ctrl.apply_setting("samp", int(float(self.ctrl.view.sink.tb_var_samp.get())))
