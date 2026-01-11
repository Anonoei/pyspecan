"""Create a tkGUI controller"""

from .. import err

from ..config import Mode, Sink
from .tkGUI.base import Controller, args_ctrl
from .tkGUI.mode_rt import ModeRT, args_rt
from .tkGUI.mode_swept import ModeSwept, args_swept
from .tkGUI.sink_file import SinkFile, args_file
from .tkGUI.sink_live import SinkLive, args_live

def GetMode(mode):
    if mode == Mode.SWEPT:
        return ModeSwept
    elif mode == Mode.RT:
        return ModeRT
    raise err.UnknownOption(f"Unknown mode: {mode}")

def GetSink(sink):
    if sink == Sink.FILE:
        return SinkFile
    elif sink == Sink.LIVE:
        return SinkLive
    raise err.UnknownOption(f"Unknown sink: {sink}")

def GetController(mode, sink):
    m: Mode = GetMode(mode) # type: ignore
    s: Sink = GetSink(sink) # type: ignore
    return lambda model, view, m=m, s=s, **kwargs: Controller(model, view, m, s, **kwargs)

def ControllerArgs(mode, sink, parser):
    args_ctrl(parser)
    if mode == Mode.SWEPT:
        args_swept(parser)
    elif mode == Mode.RT:
        args_rt(parser)

    if sink == Sink.FILE:
        args_file(parser)
    elif sink == Sink.LIVE:
        args_live(parser)
