"""Create a tkGUI view"""
from ..config import Sink
from ..utils.registry import Registry
from .tkGUI.base import View, args_view
from .tkGUI.sink_file import SinkFile, args_file
from .tkGUI.sink_live import SinkLive, args_live
from .tkGUI.sink import Sink as SinkTcpIq, args_sink as args_tcpiq

SINKS: Registry = Registry("tkGUI sink view")
SINKS.register(Sink.FILE.name)((SinkFile, args_file))
SINKS.register(Sink.LIVE.name)((SinkLive, args_live))
SINKS.register(Sink.TCPIQ.name)((SinkTcpIq, args_tcpiq))

def GetView(sink):
    sink_view = SINKS.get(sink.name)[0]
    return lambda **kwargs: View(sink_view, **kwargs)

def ViewArgs(sink, parser):
    args_view(parser)
    SINKS.get(sink.name)[1](parser)
