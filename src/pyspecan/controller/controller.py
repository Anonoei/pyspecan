import importlib

def GetController(view, mode):
    return importlib.import_module(f".controller.{view.path}", "pyspecan").GetController(mode)

def ControllerArgs(view, mode):
    return importlib.import_module(f".controller.{view.path}", "pyspecan").ControllerArgs(mode)
