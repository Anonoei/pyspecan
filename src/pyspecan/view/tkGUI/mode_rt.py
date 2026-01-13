from ...utils import args
from .mode import Mode, args_mode

def args_rt(parser):
    mode = args.get_group(parser, "Mode (RT)")
    args_mode(mode)

class ModeRT(Mode):
    def __init__(self, view, **kwargs):
        super().__init__(view, **kwargs)

    def draw_tb(self, parent, col=0):
        return col
    def draw_cl(self, parent, col=0):
        return col
