"""Create a CUI view"""
import os
import shutil
import sys

from ...utils import args
from ..base import View as _View

class ViewConfig:
    width = 0   # 0: the terminal's
    height = 0

def args_view(parser):
    view = args.get_group(parser, "View (CUI)")
    view.add_argument("--width", default=ViewConfig.width, type=int, help="plot width in characters, 0 to use the terminal's")
    view.add_argument("--height", default=ViewConfig.height, type=int, help="plot height in lines, 0 to use the terminal's")
    view.add_argument("--no-color", action="store_true", help="draw without colors")
    return view

class View(_View):
    """Console view: reads commands, draws plots as text"""
    def __init__(self, **kwargs):
        self.running = True
        self.tty = sys.stdout.isatty()
        self.use_color = self.tty and not kwargs.get("no_color") and "NO_COLOR" not in os.environ
        self._width = int(kwargs.get("width") or ViewConfig.width)
        self._height = int(kwargs.get("height") or ViewConfig.height)

    def size(self) -> tuple[int, int]:
        """(width, height) available for plots"""
        cols, lines = shutil.get_terminal_size((100, 32))
        return (self._width or min(cols, 160)), (self._height or max(lines - 3, 8))

    def mainloop(self):
        while self.running:
            try:
                self.menu()
            except EOFError:
                break
            except KeyboardInterrupt:
                print()

    def menu(self):
        pass

    def quit(self):
        self.running = False
