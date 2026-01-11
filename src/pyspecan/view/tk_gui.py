"""Create a tkGUI view"""

from ..config import Mode, Sink
from .tkGUI.base import View
from .tkGUI.sink_file import ViewFile
from .tkGUI.sink_live import ViewLive

def GetView(mode, sink):
    if sink == Sink.FILE:
        return ViewFile
    elif sink == Sink.LIVE:
        return ViewLive
    return View
