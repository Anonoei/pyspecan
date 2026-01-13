from ...utils import args
from .mode import Mode, args_mode

def args_swept(parser):
    mode = args.get_group(parser, "Mode (SWEPT)")
    args_mode(mode)

class ModeSwept(Mode):
    pass
