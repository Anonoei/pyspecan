from ..config import Sink as _Sink
from ..utils import args
from ..utils.registry import Registry
from .base import Model, args_model
from .sink import SinkFile, SinkLive, SinkTcpIq, args_file, args_live, args_tcpiq
from .sink.sink import args_sink

SINKS: Registry = Registry("sink")
SINKS.register(_Sink.FILE.name)((SinkFile, args_file))
SINKS.register(_Sink.LIVE.name)((SinkLive, args_live))
SINKS.register(_Sink.TCPIQ.name)((SinkTcpIq, args_tcpiq))

def GetSink(sink: _Sink):
    return SINKS.get(sink.name)[0]

def GetModel(sink: _Sink):
    sink_cls = GetSink(sink)
    return lambda **kwargs: Model(sink_cls, **kwargs)

def ModelArgs(sink: _Sink, parser):
    args_model(parser)
    group = args.get_group(parser, f"Sink ({sink.name})")
    args_sink(group)
    SINKS.get(sink.name)[1](group)
