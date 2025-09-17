import importlib

def GetView(view, mode):
    return importlib.import_module(f".view.{view.path}", "pyspecan").GetView(mode)
