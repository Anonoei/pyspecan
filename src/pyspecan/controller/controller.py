import importlib

def GetController(view, mode, sink):
    return importlib.import_module(f".controller.{view.path}", "pyspecan").GetController(mode, sink)

def ControllerArgs(view, mode, sink, parser):
    return importlib.import_module(f".controller.{view.path}", "pyspecan").ControllerArgs(mode, sink, parser)
