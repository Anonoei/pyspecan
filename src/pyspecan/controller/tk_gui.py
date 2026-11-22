"""Create a tkGUI controller"""
from ..config import Sink
from ..utils.registry import Registry
from .base import args_controller
from .tkGUI.base import Controller, args_ctrl
from .tkGUI.sink_file import SinkFile
from .tkGUI.sink_live import SinkLive
from .tkGUI.sink_tcpiq import SinkTcpIq

SINKS: Registry = Registry("tkGUI sink controller")
SINKS.register(Sink.FILE.name)(SinkFile)
SINKS.register(Sink.LIVE.name)(SinkLive)
SINKS.register(Sink.TCPIQ.name)(SinkTcpIq)

def GetController(sink):
    sink_ctrl = SINKS.get(sink.name)
    return lambda model, view, **kwargs: Controller(model, view, sink_ctrl, **kwargs)

def ControllerArgs(sink, parser):
    args_controller(parser)
    args_ctrl(parser)
