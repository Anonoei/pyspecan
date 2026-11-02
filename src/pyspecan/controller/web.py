"""Create a web controller"""
from .. import err
from ..config import Mode, Sink
from .WEB.base import Controller, args_ctrl

def GetController(mode, sink):
    if mode != Mode.SWEPT or sink != Sink.FILE:
        raise err.UnknownOption(f"WEB view only supports swept mode with a file sink, got {mode.name}/{sink.name}")
    return Controller

def ControllerArgs(mode, sink, parser):
    args_ctrl(parser)
