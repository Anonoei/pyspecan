from typing import Callable

from .. import err
from ..config import config
from ..config import Mode as _Mode
from ..config import Sink as _Sink

from .base import Model, args_model
from .mode import Mode
from .mode import ModeSwept, args_swept
from .mode import ModeRT, args_rt
from .sink import Sink
from .sink import SinkFile, args_file
from .sink import SinkLive, args_live

def GetMode(mode):
    if mode == _Mode.SWEPT:
        return ModeSwept
    elif mode == _Mode.RT:
        return ModeRT
    raise err.UnknownOption(f"Unknown mode: {mode}")

def GetSink(sink):
    if sink == _Sink.FILE:
        return SinkFile
    elif sink == _Sink.LIVE:
        return SinkLive
    raise err.UnknownOption(f"Unknown sink: {sink}")

def GetModel(mode, sink):
    mode = GetMode(mode)
    sink = GetSink(sink)
    return lambda m=mode, s=sink, **kwargs: Model(m, s, **kwargs)

def ModelArgs(mode, sink, parser):
    args_model(parser)
    if mode == _Mode.SWEPT:
        args_swept(parser)
    elif mode == _Mode.RT:
        args_rt(parser)

    if sink == _Sink.FILE:
        args_file(parser)
    elif sink == _Sink.LIVE:
        args_live(parser)
