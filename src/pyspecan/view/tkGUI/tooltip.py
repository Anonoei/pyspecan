"""A tooltip: a small borderless window of text beside a widget or a menu entry"""
import tkinter as tk

class Tooltip:
    """One floating label, shown with `show(text, x, y)` (screen coordinates) and hidden with `hide()`.
    `attach(widget, text)` shows it while the pointer is over a widget (text may be a callable, read each time)"""
    def __init__(self, root, wrap: int = 420):
        self.root = root
        self.wrap = wrap
        self.win: tk.Toplevel | None = None

    def show(self, text: str, x: int, y: int):
        if not text:
            self.hide()
            return
        if self.win is None:
            self.win = tk.Toplevel(self.root)
            self.win.wm_overrideredirect(True)
            try:
                self.win.attributes("-topmost", True)
            except tk.TclError:
                pass
            self.label = tk.Label(self.win, justify=tk.LEFT, background="#1b1b1b", foreground="#eeeeee", relief=tk.SOLID,
                                  borderwidth=1, padx=8, pady=6, wraplength=self.wrap, font=("TkDefaultFont", 9))
            self.label.pack()
        self.label.config(text=text)
        # keep it on the screen
        self.win.update_idletasks()
        w, h = self.win.winfo_reqwidth(), self.win.winfo_reqheight()
        sw, sh = self.root.winfo_screenwidth(), self.root.winfo_screenheight()
        self.win.geometry(f"+{max(0, min(x, sw - w))}+{max(0, min(y, sh - h))}")
        self.win.deiconify()
        self.win.lift()

    def hide(self):
        if self.win is not None:
            self.win.withdraw()

    def attach(self, widget, text):
        def enter(_e):
            t = text() if callable(text) else text
            self.show(t, widget.winfo_rootx(), widget.winfo_rooty() + widget.winfo_height() + 4)
        widget.bind("<Enter>", enter, add="+")
        widget.bind("<Leave>", lambda _e: self.hide(), add="+")
        widget.bind("<ButtonPress>", lambda _e: self.hide(), add="+")
