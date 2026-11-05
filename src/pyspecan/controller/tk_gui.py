"""Create a tkGUI controller"""
from ..config import Sink
from ..utils.registry import Registry
from .tkGUI.base import Controller, args_ctrl
from .tkGUI.sink_file import SinkFile, args_file
from .tkGUI.sink_live import SinkLive, args_live

SINKS: Registry = Registry("tkGUI sink controller")
SINKS.register(Sink.FILE.name)((SinkFile, args_file))
SINKS.register(Sink.LIVE.name)((SinkLive, args_live))

def GetController(sink):
    sink_ctrl = SINKS.get(sink.name)[0]
    return lambda model, view, **kwargs: Controller(model, view, sink_ctrl, **kwargs)

def ControllerArgs(sink, parser):
    args_ctrl(parser)
    SINKS.get(sink.name)[1](parser)
