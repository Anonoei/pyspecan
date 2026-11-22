"""CUI Controller: a command line over the shared controller core, plots are drawn as text"""
import pathlib
import shlex
import shutil
import textwrap

from ...model.model import Model
from ...plots import PLOTS, Scroller, layout
from ...plots.frame import IMAGE, LINE, SCATTER, Frame
from ...plots.freq import fmt_hz
from ...view.CUI.base import View as CUI
from ...view.CUI.base import args_view
from ...view.CUI.draw import draw_frame
from ..base import Controller as _Controller


def args_ctrl(parser):
    args_view(parser)

class Controller(_Controller):
    """CUI Controller"""
    FEATURES = {LINE, SCATTER, IMAGE}

    def __init__(self, model: Model, view: CUI, **kwargs):
        super().__init__(model, view, **kwargs)
        self.view: CUI = self.view # type hints
        self.view.menu = self.menu
        self.frames: dict[str, tuple[Frame, list]] = {} # plot id -> latest frame and its images
        self.scrollers: dict[tuple, Scroller] = {}

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
            (("radios",), "radios", "list the radios that can be used, and how to pick one", self.cmd_radios),
            (("device", "dev"), "device <target>", "use a radio: a driver, or tcp://host:5555/<id>", self.cmd_device),
            (("antenna", "ant"), "antenna [port]", "list the radio's receive antennas, or select one", self.cmd_antenna),
            (("claim",), "claim", "take control of a hosted radio that is free", lambda a: self._radio_cmd("claim")),
            (("release",), "release", "give up control of a hosted radio, and keep watching", lambda a: self._radio_cmd("release")),
            (("reconnect",), "reconnect", "connect to the radio again", lambda a: self._radio_cmd("reconnect")),
            (("record", "rec"), "record [path|stop]", "record what the radio delivers while playing (default: SigMF in --record_dir)",
             self.cmd_record),
            (("fs",), "fs <rate|measured>", "sample rate, e.g. 250k; `measured`: the rate a TCP IQ stream arrives at", self.cmd_fs),
            (("cf",), "cf <freq>", "center frequency", self.cmd_cf),
            (("nfft",), "nfft <n>", "FFT size, a power of two (or its exponent)", self.cmd_nfft),
            (("sweep",), "sweep <ms>", "ms of samples per block", self.cmd_sweep),
            (("overlap",), "overlap <0-1>", "overlap of realtime frames", self.cmd_overlap),
            (("show",), "show <ms>", "ms between frames while playing", self.cmd_show),
            (("plots", "ls"), "plots", "list the plots and their settings", self.cmd_plots),
            (("types",), "types", "list the plots that can be added, by category", self.cmd_types),
            (("about",), "about <type>", "what a plot does: its data, what it shows, what to use it for, its cost", self.cmd_about),
            (("add",), "add <type>", "add a plot, e.g. add Spectrogram", self.cmd_add),
            (("del", "rm"), "del <id>", "remove a plot", self.cmd_del),
            (("type",), "type <id> <type>", "change a plot's type", self.cmd_type),
            (("move", "mv"), "move <id> <where> [target]", "left|right|above|below <target>, or end for a new row at the bottom", self.cmd_move),
            (("marker", "mk"), "marker <id> add|set|del|act|kinds ...", "markers and measurements: add <kind> [key=value ...], set <marker> <key> <value>, del <marker>, act <marker> next|prev|left|right (peak)", self.cmd_marker),
            (("set",), "set <id> <key> <value>", "change a plot setting, e.g. set p1 vbw 5", self.cmd_set),
            (("export",), "export <id> csv|table|json|txt <file>", "save a plot's latest frame: its traces or table as CSV, all of it as JSON, its drawing as text", self.cmd_export),
            (("act",), "act <id> <action>", "a plot's action, like a PSD's: act p1 store ref (see plots for each one's actions)", self.cmd_act),
            (("link",), "link <id> <target>", "link two plots: they share ref level, scale, vbw, window, unit and markers", self.cmd_link),
            (("unlink",), "unlink <id>", "take a plot out of its link", self.cmd_unlink),
            (("cal",), "cal <key> <value>", "set a global (every plot) setting: cal_db, ext_gain", self.cmd_cal),
            (("save",), "save <file>", "save the plots, their settings, links and markers (relaunch with --layout <file>)", self.cmd_save),
            (("load",), "load <file>", "replace the plots by a saved layout", self.cmd_load),
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
        for _, (frame, images) in shown:
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
        except Exception as e: # also what the radio library raises (Busy, NotController...)
            print(f"error: {type(e).__name__}: {e}" if not isinstance(e, ValueError) else f"error: {e}")

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
        radio = st.get("radio")
        if radio:
            print(f"  radio {radio['device']} ({radio['control']}{', ' + str(radio['lag']) + ' s behind' if radio['lag'] else ''}{', spectrum mirrored, corrected' if radio.get('inverted') else ''})")
            for a in radio.get("antennas", []):
                print(f"    antenna {'*' if a['selected'] else ' '} {a['label']}")
            if radio["dropped"]:
                print(f"    {radio['dropped']:,} samples lost by the radio")
            if radio["recording"]:
                print(f"    recording {radio['recording']['seconds']:g} s to {radio['recording']['path']}")
            elif radio["record_error"]:
                print(f"    {radio['record_error']}")
        stream = st.get("stream")
        if stream:
            line = f"  stream from {stream['peer'] or '(waiting for a sender)'}"
            if stream["measured"]:
                line += f", arriving at {fmt_hz(stream['measured']).replace('Hz', 'S/s')}" + (" (not the declared rate: `fs measured` uses it)" if stream["mismatch"] else "")
            print(line)
        if "path" in st:
            print(f"  file {st['path'] or '-'}  format {st['fmt']}  at {st['cur_samp']}/{st['max_samp']}  {st['time_cur']} / {st['time_tot']}")
        if self.message:
            print(f"  {self.message}")

    def cmd_radios(self, args):
        for r in self.radios():
            print(f"  {r['label']:<70} device {r['target']}" if r["target"] else f"  {r['label']}")

    def cmd_device(self, args):
        self._need(args, 1, "device <target>")
        self.setting("device", args[0])
        self.cmd_status([])

    def cmd_antenna(self, args):
        """antenna [port]: list the receive antennas of the radio, or select one"""
        self._need_radio_ports()
        if args:
            self.setting("antenna", " ".join(args))
        for a in self.sink.antennas():
            print(f"  {'*' if a['selected'] else ' '} {a['label']}{'  (spectrum mirrored, corrected)' if a['inverted'] else ''}")

    def _need_radio_ports(self):
        if self.sink.status() is None:
            raise ValueError("the sink is a file, there is no radio")
        if not self.sink.antennas():
            raise ValueError("this radio has no selectable antennas")

    def cmd_record(self, args):
        """record [path|stop]: record the radio's samples while playing, or stop recording"""
        if args and args[0] == "stop":
            self.stop_record()
            print(f"  {self.message}")
            return
        path = self.start_record(" ".join(args) or None)
        self.playing = False # here playing is the `start` loop, which is what reads (and so records)
        print(f"  recording to {path}: `start` plays and records, `record stop` ends it")

    def _radio_cmd(self, cmd):
        self.command(cmd)
        self.cmd_status([])

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
        self._need(args, 1, "fs <rate|measured>")
        self.setting("fs", args[0])
        if args[0].strip().lower() == "measured":
            print(f"  fs {self.model.get_fs()}")

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
        print("  global  " + "  ".join(f"{k}={v}" for k, v in self.plots.globals.items()))
        for pid, plot in self.plots:
            link = f" [{plot.link.id}]" if plot.link is not None else ""
            values = plot.settings()
            print(f"  {pid:<4} {plot.NAME}{link}{'' if values['enabled'] else ' (paused)'}")
            groups: dict[str, list[str]] = {}
            for s in plot.SETTINGS:
                mark = "*" if plot.link is not None and s.scope == "link" else ""
                groups.setdefault(s.group, []).append(f"{s.key}{mark}={values[s.key]}")
            for name, items in groups.items():
                print(f"       {name:<12} " + "  ".join(items))

    def cmd_link(self, args):
        self._need(args, 2, "link <id> <target>")
        print(f"  {args[0]} -> {self.link_plot(args[0], args[1])}")

    def cmd_unlink(self, args):
        self._need(args, 1, "unlink <id>")
        self.unlink_plot(args[0])

    def cmd_cal(self, args):
        self._need(args, 2, "cal <key> <value>")
        self.setting(args[0], args[1])

    def cmd_save(self, args):
        self._need(args, 1, "save <file>")
        path = pathlib.Path(" ".join(args)).expanduser()
        path.write_text(self.save_layout() + "\n")
        print(f"  saved {path}")

    def cmd_load(self, args):
        self._need(args, 1, "load <file>")
        self.load_layout(pathlib.Path(" ".join(args)).expanduser().read_text())
        self.frames.clear()
        self.scrollers.clear()
        self.cmd_plots([])

    def cmd_types(self, args):
        """The plot types by category, each with what it shows (cut to the line)"""
        info = self.plot_info()
        width = shutil.get_terminal_size((100, 20)).columns
        for category, names in self.plot_groups():
            print(f"  {category}")
            for n in names:
                line = f"    {n:<22} {info[n]['shows']}"
                print(line if len(line) <= width else line[:width - 1] + "…")
        print("  about <type> tells more")

    def cmd_about(self, args):
        self._need(args, 1, "about <type>")
        from ...plots.base import about_text  # plain text, as the tk tooltip
        name = layout.resolve_type(" ".join(args))
        width = shutil.get_terminal_size((100, 20)).columns
        for line in about_text(name, self.plot_info().get(name) or PLOTS.get(name).about()).split("\n"):
            print(textwrap.fill(line, width - 2, initial_indent="  ", subsequent_indent="      "))

    def cmd_add(self, args):
        self._need(args, 1, "add <type>")
        print(f"  added {self.add_plot(layout.resolve_type(' '.join(args)))}")

    def cmd_del(self, args):
        self._need(args, 1, "del <id>")
        self.del_plot(args[0])
        self.frames.pop(args[0], None)

    def cmd_type(self, args):
        self._need(args, 2, "type <id> <type>")
        self.set_plot_type(args[0], layout.resolve_type(" ".join(args[1:])))
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

    def cmd_marker(self, args):
        self._need(args, 2, "marker <id> add <kind> [key=value ...] | set <marker> <key> <value> | del <marker> | act <marker> <action> | kinds")
        pid, op, rest = args[0], args[1].lower(), args[2:]
        if op == "kinds":
            for kind, fields in self.plots.get(pid).markers.kinds().items():
                print(f"  {kind:<8} " + "  ".join(f["key"] for f in fields))
        elif op == "add":
            self._need(rest, 1, "marker <id> add <kind> [key=value ...]")
            params = dict(kv.split("=", 1) for kv in rest[1:] if "=" in kv)
            print(f"  added {self.add_marker(pid, rest[0], **params)}")
        elif op == "set":
            self._need(rest, 3, "marker <id> set <marker> <key> <value>")
            self.set_marker(pid, rest[0], rest[1], " ".join(rest[2:]))
        elif op in ("del", "rm"):
            self._need(rest, 1, "marker <id> del <marker>")
            self.del_marker(pid, rest[0])
        elif op == "act":
            self._need(rest, 2, "marker <id> act <marker> <action> (a peak marker: prev, next, left, right)")
            self.marker_action(pid, rest[0], rest[1].lower())
        else:
            raise ValueError("usage: marker <id> add|set|del|act|kinds ...")

    def cmd_export(self, args):
        self._need(args, 3, "export <id> csv|table|json|txt <file>")
        pid, what, path = args[0], args[1].lower(), pathlib.Path(" ".join(args[2:])).expanduser()
        if what == "txt": # the drawing, as this console shows it (without colors)
            if pid not in self.frames:
                raise ValueError(f"{pid} has drawn nothing yet: step or play first")
            frame, images = self.frames[pid]
            width, height = self.view.size()
            text = "\n".join(draw_frame(frame, images, width, height, use_color=False)) + "\n"
        else:
            text = self.export(pid, what)
        path.write_text(text, encoding="utf-8")
        print(f"  saved {path}")

    def cmd_act(self, args):
        self._need(args, 2, "act <id> <action>")
        self.plot_action(args[0], " ".join(args[1:]))

    def cmd_set(self, args):
        self._need(args, 3, "set <id> <key> <value>")
        self.set_plot(args[0], args[1], " ".join(args[2:]))
        self.cmd_plots([])
