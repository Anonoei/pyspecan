import importlib

def GetView(view, sink):
    return importlib.import_module(f".view.{view.path}", "pyspecan").GetView(sink)
