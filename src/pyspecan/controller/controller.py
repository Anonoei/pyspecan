import importlib

def GetController(view, sink):
    return importlib.import_module(f".controller.{view.path}", "pyspecan").GetController(sink)

def ControllerArgs(view, sink, parser):
    return importlib.import_module(f".controller.{view.path}", "pyspecan").ControllerArgs(sink, parser)
