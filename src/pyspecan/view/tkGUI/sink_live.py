import tkinter as tk
import tkinter.ttk as ttk

from .sink import Sink


class SinkLive(Sink):
    __slots__ = (
        # control panel
        "cl_var_dev", "cl_cb_dev", "cl_lbl_status", "cl_btn_claim", "cl_btn_reconnect", "cl_btn_record", "cl_lbl_live",
        "cl_var_rx", "cl_ent_rx",
        "cl_fr_stages", "cl_stage_vars", "cl_stage_ents",
        "cl_lbl_ant", "cl_var_ant", "cl_cb_ant"
    )
    def __init__(self, view, **kwargs):
        super().__init__(view, **kwargs)
        self.cl_var_dev: tk.StringVar = None # type: ignore
        self.cl_cb_dev: ttk.Combobox = None # type: ignore
        self.cl_var_rx: tk.StringVar = None # type: ignore
        self.cl_ent_rx: ttk.Entry = None # type: ignore
        self.cl_fr_stages: ttk.Frame = None # type: ignore
        self.cl_lbl_ant: ttk.Label = None # type: ignore
        self.cl_var_ant: tk.StringVar = None # type: ignore
        self.cl_cb_ant: ttk.Combobox = None # type: ignore
        self.cl_stage_vars: dict[str, tk.StringVar] = {}
        self.cl_stage_ents: dict[str, ttk.Entry] = {}

    def draw_cl(self, parent, row=0):
        parent.columnconfigure(1, weight=1)
        self.cl_var_dev = tk.StringVar(parent)
        ttk.Label(parent, text="Device:").grid(row=row,column=0, sticky=tk.W)
        self.cl_cb_dev = ttk.Combobox(parent, textvariable=self.cl_var_dev, width=20)
        self.cl_cb_dev.grid(row=row,column=1, sticky=tk.NSEW)
        row += 1
        self.cl_lbl_status = ttk.Label(parent, text="", wraplength=220, justify=tk.LEFT)
        self.cl_lbl_status.grid(row=row,column=0,columnspan=2, sticky=tk.W)
        row += 1
        buttons = ttk.Frame(parent)
        buttons.grid(row=row,column=0,columnspan=2, sticky=tk.EW)
        self.cl_btn_claim = ttk.Button(buttons, text="Claim")
        self.cl_btn_claim.pack(side=tk.LEFT)
        self.cl_btn_reconnect = ttk.Button(buttons, text="Reconnect")
        self.cl_btn_reconnect.pack(side=tk.LEFT, padx=4)
        self.cl_btn_record = ttk.Button(buttons, text="Record")
        self.cl_btn_record.pack(side=tk.LEFT)
        row += 1
        self.cl_lbl_live = ttk.Label(parent, text="", wraplength=220, justify=tk.LEFT) # samples lost, the recording
        self.cl_lbl_live.grid(row=row,column=0,columnspan=2, sticky=tk.W)
        row += 1
        ttk.Separator(parent, orient=tk.HORIZONTAL).grid(row=row, column=0, columnspan=2, pady=5, sticky=tk.EW)
        row += 1
        self.cl_lbl_ant = ttk.Label(parent, text="Antenna:")
        self.cl_var_ant = tk.StringVar(parent)
        self.cl_cb_ant = ttk.Combobox(parent, textvariable=self.cl_var_ant, width=20, state="readonly")
        self.cl_lbl_ant.grid(row=row,column=0, sticky=tk.W)
        self.cl_cb_ant.grid(row=row,column=1, sticky=tk.NSEW)
        row += 1
        self.cl_var_rx = tk.StringVar(parent)
        ttk.Label(parent, text="Rx Gain (0-1):").grid(row=row,column=0, sticky=tk.W)
        self.cl_ent_rx = ttk.Entry(parent, textvariable=self.cl_var_rx, width=5)
        self.cl_ent_rx.grid(row=row,column=1, sticky=tk.E)
        row += 1
        self.cl_fr_stages = ttk.Frame(parent)
        self.cl_fr_stages.columnconfigure(1, weight=1)
        self.cl_fr_stages.grid(row=row,column=0,columnspan=2, sticky=tk.NSEW)
        return row

    def set_antennas(self, labels, selected):
        """The antenna choices (hidden when the radio has none to choose from), `selected`: the label in use"""
        if not labels:
            self.cl_lbl_ant.grid_remove()
            self.cl_cb_ant.grid_remove()
            return
        self.cl_lbl_ant.grid()
        self.cl_cb_ant.grid()
        self.cl_cb_ant.config(values=labels)
        self.cl_var_ant.set(selected or "")

    def set_stages(self, stages):
        """Rebuild the gain stage entries from {name: GainStage}, as declared by the device"""
        for w in self.cl_fr_stages.winfo_children():
            w.destroy()
        self.cl_stage_vars = {}
        self.cl_stage_ents = {}
        for i, name in enumerate(stages):
            var = tk.StringVar(self.cl_fr_stages)
            ttk.Label(self.cl_fr_stages, text=f"Rx {name} Gain (dB):").grid(row=i,column=0, sticky=tk.W)
            ent = ttk.Entry(self.cl_fr_stages, textvariable=var, width=5)
            ent.grid(row=i,column=1, sticky=tk.E)
            self.cl_stage_vars[name] = var
            self.cl_stage_ents[name] = ent
        return self.cl_stage_ents
