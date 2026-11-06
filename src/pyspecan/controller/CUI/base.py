"""CUI Controller: a command line over the shared controller core, plots are drawn as text"""
import shlex

from ...plots import Scroller
from ...plots.frame import Frame, LINE, SCATTER, IMAGE
from ...view.CUI.base import View as CUI, args_view
from ...view.CUI.draw import draw_frame
from ...model.model import Model
from ..base import Controller as _Controller, ControllerConfig

def args_ctrl(parser):
    args_view(parser)
    ctrl = parser.add_argument_group("Controller (CUI)")
    ctrl.add_argument("--show", default=ControllerConfig.show, type=float, help="[ms] time between frames while playing")
    return ctrl

class Controller(_Controller):
    """CUI Controller"""
    FEATURES = {LINE, SCATTER, IMAGE}

    def __init__(self, model: Model, view: CUI, **kwargs):
        super().__init__(model, view, **kwargs)
        self.view: CUI = self.view # type hints
        self.view.menu = self.menu
        self.frames: dict[str, tuple[Frame, list]] = {} # plot id -> latest frame and its images
        self.scrollers: dict[tuple, Scroller] = {}
        self.add_plot("PSD")

        # name -> (usage, help, handler), the first name is the canonical one
        self.commands = {}
        for names, usage, text, fn in (
            (("help", "h", "?"), "help", "show this message", self.cmd_help),
            (("quit", "q", "exit"), "quit", "exit", self.cmd_quit),
            (("status", "s"), "status", "show the settings and the sample position", self.cmd_status),
            (("draw", "d"), "draw", "draw the plots again", self.cmd_draw),
            (("start", "play"), "start [ticks]", "play until the end of the data, ctrl-c or [ticks] frames", self.cmd_start),
            (("next", "n"), "next", "read and draw the next block", self.cmd_next),
            (("prev", "p"), "prev", "read and draw the previous block", self.cmd_prev),
            (("reset",), "reset", "rewind and clear the plots", self.cmd_reset),
            (("seek",), "seek <sample>", "jump to a sample", self.cmd_seek),
            (("open", "path", "f"), "open <path>", "open a file", self.cmd_open),
            (("fmt",), "fmt <format>", "file format", self.cmd_fmt),
            (("fs",), "fs <rate>", "sample rate, e.g. 250k", self.cmd_fs),
            (("cf",), "cf <freq>", "center frequency", self.cmd_cf),
            (("nfft",), "nfft <n>", "FFT size, a power of two (or its exponent)", self.cmd_nfft),
            (("sweep",), "sweep <ms>", "ms of samples per block", self.cmd_sweep),
            (("overlap",), "overlap <0-1>", "overlap of realtime frames", self.cmd_overlap),
            (("show",), "show <ms>", "ms between frames while playing", self.cmd_show),
            (("plots", "ls"), "plots", "list the plots and their settings", self.cmd_plots),
            (("types",), "types", "list the plots that can be added", self.cmd_types),
            (("add",), "add <type>", "add a plot, e.g. add Spectrogram", self.cmd_add),
            (("del", "rm"), "del <id>", "remove a plot", self.cmd_del),
            (("type",), "type <id> <type>", "change a plot's type", self.cmd_type),
            (("move", "mv"), "move <id> <where> [target]", "left|right|above|below <target>, or end for a new row at the bottom", self.cmd_move),
            (("set",), "set <id> <key> <value>", "change a plot setting, e.g. set p1 vbw 5", self.cmd_set),
        ):
            for name in names:
                self.commands[name] = (usage, text, fn)

    # --- core hooks --- #
    def deliver(self, frames, status):
        # image histories advance every tick, whether or not the frame gets drawn
        for pid, frame in frames.items():
            images = [self.scrollers.setdefault((pid, i), Scroller()).apply(ax.image) if ax.image else None
                      for i, ax in enumerate(frame.axes)]
            self.frames[pid] = (frame, images)

    # --- drawing --- #
    def draw(self, clear=False):
        width, height = self.view.size()
        shown = [(pid, self.frames[pid]) for pid, _ in self.plots if pid in self.frames]
        if not shown:
            print("nothing to draw yet, read a block first (next / start)")
            return
        per = max((height - len(shown)) // len(shown), 4)
        lines = []
        for pid, (frame, images) in shown:
            lines += draw_frame(frame, images, width, per, self.view.use_color)
        out = "\n".join(lines)
        if clear and self.view.tty:
            out = "\x1b[H" + out.replace("\n", "\x1b[K\n") + "\x1b[K\x1b[J"
        print(out, flush=True)

    # --- repl --- #
    def menu(self):
        try:
            line = input("pyspecan > ")
        except EOFError:
            self.view.quit()
            raise
        try:
            argv = shlex.split(line)
        except ValueError as e:
            print(f"error: {e}")
            return
        if not argv:
            return
        cmd, args = argv[0].lower(), argv[1:]
        if cmd not in self.commands:
            print(f"unknown command {cmd!r}, try help")
            return
        try:
            self.commands[cmd][2](args)
        except (ValueError, KeyError, TypeError, OSError) as e:
            print(f"error: {e}")

    def _need(self, args, n, usage):
        if len(args) < n:
            raise ValueError(f"usage: {usage}")

    def cmd_help(self, args):
        seen = set()
        for usage, text, _ in self.commands.values():
            if usage not in seen:
                seen.add(usage)
                print(f"  {usage:<26} {text}")

    def cmd_quit(self, args):
        self.quit()
        self.view.quit()

    def cmd_status(self, args):
        st = self.get_state()
        print(f"  sink {st['sink']}  fs {st['fs']}  cf {st['cf']}  nfft {st['nfft']}  overlap {st['overlap']}")
        print(f"  block {st['block_size']} samples ({st['sweep']} ms, asked for {st['sweep_samples']})  show {st['show']} ms")
        if "path" in st:
            print(f"  file {st['path'] or '-'}  format {st['fmt']}  at {st['cur_samp']}/{st['max_samp']}  {st['time_cur']} / {st['time_tot']}")
        if self.message:
            print(f"  {self.message}")

    def cmd_draw(self, args):
        self.draw()

    def _read(self, cmd):
        self.command(cmd)
        if self.message:
            print(self.message)
        self.draw()

    def cmd_next(self, args):
        self._read("next")

    def cmd_prev(self, args):
        self._read("prev")

    def cmd_reset(self, args):
        self.command("reset")
        self.frames.clear()
        self.scrollers.clear()
        print("reset")

    def cmd_start(self, args):
        limit = int(args[0]) if args else None
        self.command("start")
        count = 0
        try:
            while self.playing and (limit is None or count < limit):
                if not self.tick():
                    break
                count += 1
                if self.view.tty:
                    self.draw(clear=True)
        except KeyboardInterrupt:
            pass
        finally:
            self.playing = False
        if self.message:
            print(self.message)
        if not self.view.tty:
            self.draw()

    def cmd_seek(self, args):
        self._need(args, 1, "seek <sample>")
        self.setting("samp", args[0])

    def cmd_open(self, args):
        self._need(args, 1, "open <path>")
        self.setting("path", " ".join(args))
        self.cmd_status([])

    def cmd_fmt(self, args):
        self._need(args, 1, "fmt <format>")
        self.setting("fmt", args[0])

    def cmd_fs(self, args):
        self._need(args, 1, "fs <rate>")
        self.setting("fs", args[0])

    def cmd_cf(self, args):
        self._need(args, 1, "cf <freq>")
        self.setting("cf", args[0])

    def cmd_nfft(self, args):
        self._need(args, 1, "nfft <n>")
        n = int(args[0])
        if n > 20: # a size, not an exponent
            if n & (n - 1):
                raise ValueError("nfft must be a power of two")
            n = n.bit_length() - 1
        self.setting("nfft_exp", n)

    def cmd_sweep(self, args):
        self._need(args, 1, "sweep <ms>")
        self.setting("sweep", args[0])

    def cmd_overlap(self, args):
        self._need(args, 1, "overlap <0-1>")
        self.setting("overlap", args[0])

    def cmd_show(self, args):
        self._need(args, 1, "show <ms>")
        self.setting("show", args[0])

    # --- plots --- #
    def cmd_plots(self, args):
        for pid, plot in self.plots:
            vals = "  ".join(f"{k}={v}" for k, v in plot.settings().items())
            print(f"  {pid:<4} {plot.NAME:<12} {vals}")

    def cmd_types(self, args):
        print("  " + ", ".join(self.plot_types))

    def cmd_add(self, args):
        self._need(args, 1, "add <type>")
        name = " ".join(args)
        match = {t.lower(): t for t in self.plot_types}.get(name.lower())
        print(f"  added {self.add_plot(match or name)}")

    def cmd_del(self, args):
        self._need(args, 1, "del <id>")
        self.del_plot(args[0])
        self.frames.pop(args[0], None)

    def cmd_type(self, args):
        self._need(args, 2, "type <id> <type>")
        name = " ".join(args[1:])
        self.set_plot_type(args[0], {t.lower(): t for t in self.plot_types}.get(name.lower(), name))
        self.frames.pop(args[0], None)
        for k in [k for k in self.scrollers if k[0] == args[0]]:
            del self.scrollers[k]

    def cmd_move(self, args):
        self._need(args, 2, "move <id> <left|right|above|below> <target>  |  move <id> end")
        where = args[1]
        if where != "end":
            self._need(args, 3, "move <id> <left|right|above|below> <target>")
        self.move_plot(args[0], args[2] if len(args) > 2 else None, where)
        print("  " + "  |  ".join(" ".join(row) for row in self.plots.layout))

    def cmd_set(self, args):
        self._need(args, 3, "set <id> <key> <value>")
        self.set_plot(args[0], args[1], " ".join(args[2:]))
        self.cmd_plots([])
