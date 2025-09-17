"""Create a tkGUI view"""

from ..config import Mode
from .tkGUI.modes import ViewSwept, ViewRT

def GetView(mode):
    if mode == Mode.SWEPT:
        return ViewSwept
    elif mode == Mode.RT:
        return ViewRT
