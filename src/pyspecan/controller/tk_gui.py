"""Create a tkGUI controller"""

from ..config import Mode
from .tkGUI.modes import ControllerSwept, ControllerRT
from .tkGUI.modes import args_swept, args_rt

def GetController(mode):
    if mode == Mode.SWEPT:
        return ControllerSwept
    elif mode == Mode.RT:
        return ControllerRT

def ControllerArgs(mode):
    if mode == Mode.SWEPT:
        return args_swept
    elif mode == Mode.RT:
        return args_rt
