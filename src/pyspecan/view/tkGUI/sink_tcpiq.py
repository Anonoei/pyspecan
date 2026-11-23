import tkinter as tk
import tkinter.ttk as ttk

from .sink import Sink


class SinkTcpIq(Sink):
    """A TCP IQ stream: who sends, the rate samples arrive at, and a button to use it"""
    __slots__ = ("cl_lbl_stream", "cl_btn_measured")
    def __init__(self, view, **kwargs):
        super().__init__(view, **kwargs)
        self.cl_lbl_stream: ttk.Label = None # type: ignore
        self.cl_btn_measured: ttk.Button = None # type: ignore

    def draw_cl(self, parent, row=0):
        parent.columnconfigure(1, weight=1)
        self.cl_lbl_stream = ttk.Label(parent, text="", wraplength=220, justify=tk.LEFT)
        self.cl_lbl_stream.grid(row=row, column=0, columnspan=2, sticky=tk.W)
        row += 1
        self.cl_btn_measured = ttk.Button(parent, text="Use measured rate", state="disabled")
        self.cl_btn_measured.grid(row=row, column=0, columnspan=2, sticky=tk.W)
        return row + 1
