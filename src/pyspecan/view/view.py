import importlib

def GetView(view, mode, sink):
    return importlib.import_module(f".view.{view.path}", "pyspecan").GetView(mode, sink)
