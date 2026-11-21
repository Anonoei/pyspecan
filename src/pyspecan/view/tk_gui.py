"""Create a tkGUI view"""
from ..config import Sink
from ..utils.registry import Registry
from .tkGUI.base import View
from .tkGUI.sink import Sink as SinkTcpIq
from .tkGUI.sink_file import SinkFile
from .tkGUI.sink_live import SinkLive

SINKS: Registry = Registry("tkGUI sink view")
SINKS.register(Sink.FILE.name)(SinkFile)
SINKS.register(Sink.LIVE.name)(SinkLive)
SINKS.register(Sink.TCPIQ.name)(SinkTcpIq)

def GetView(sink):
    sink_view = SINKS.get(sink.name)
    return lambda **kwargs: View(sink_view, **kwargs)
