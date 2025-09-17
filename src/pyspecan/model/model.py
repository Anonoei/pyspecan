from typing import Callable

from .. import err
from ..config import config, Mode

from .base import Model
from .modes import ModelSwept, ModelRT
from .modes import args_swept, args_rt

def GetModel(mode):
    if mode == Mode.SWEPT:
        return ModelSwept
    elif mode == Mode.RT:
        return ModelRT
    else:
        raise err.UnknownOption(f"Unknown mode specified: {mode}")

def ModelArgs(mode) -> Callable:
    if mode == Mode.SWEPT:
        return args_swept
    elif mode == Mode.RT:
        return args_rt
    else:
        raise err.UnknownOption(f"Unknown mode specified: {mode}")
