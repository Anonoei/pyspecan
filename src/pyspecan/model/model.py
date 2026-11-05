from ..config import Sink as _Sink
from ..utils.registry import Registry

from .base import Model, args_model
from .sink import SinkFile, args_file
from .sink import SinkLive, args_live

SINKS: Registry = Registry("sink")
SINKS.register(_Sink.FILE.name)((SinkFile, args_file))
SINKS.register(_Sink.LIVE.name)((SinkLive, args_live))

def GetSink(sink: _Sink):
    return SINKS.get(sink.name)[0]

def GetModel(sink: _Sink):
    sink_cls = GetSink(sink)
    return lambda **kwargs: Model(sink_cls, **kwargs)

def ModelArgs(sink: _Sink, parser):
    args_model(parser)
    SINKS.get(sink.name)[1](parser)
