import tkinter as tk
import tkinter.ttk as ttk

class Scale(ttk.Frame):
    def __init__(self, master=None, **kw):
        ttk.Frame.__init__(self, master)
        self.columnconfigure(0, weight=1)

        from_ = kw.pop("from_", 0)
        to = kw.pop("to", 10)

        self._var = kw.pop("variable", tk.IntVar(master))
        self._var.set(from_)
        self._last_valid = from_

        self.label = ttk.Label(self)
        self.scale = ttk.Scale(self, variable=self._var, from_=from_, to=to, **kw)
        self.scale.bind('<<RangeChanged>>', self._adjust)

        self.scale.pack(side=tk.BOTTOM, fill=tk.X)

        dummy = ttk.Label(self)
        dummy.pack(side=tk.TOP)
        dummy.lower()
        self.label.place(anchor=tk.N)

        self.__tracecb = self._var.trace_add('write', self._adjust)
        self.bind('<Configure>', self._adjust)
        self.bind('<Map>', self._adjust)

    def _adjust(self, *args):
        def adjust_label():
            self.update_idletasks()

            x, y = self.scale.coords()
            y = self.scale.winfo_y() - self.label.winfo_reqheight()
            self.label.place_configure(x=x, y=y)
        from_ = ttk._to_number(self.scale["from"]) # type: ignore
        to = ttk._to_number(self.scale["to"]) # type: ignore
        if to < from_:
            from_, to = to, from_
        newval = self._var.get()
        if not from_ <= newval <= to:
            self.value = self._last_valid
            return
        self._last_valid = newval
        self.label["text"] = newval
        self.after_idle(adjust_label)
