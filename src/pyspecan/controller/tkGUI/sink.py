from ... import logger

def args_sink(parser):
    pass

class Sink:
    def __init__(self, ctrl):
        self.log = logger.new(f"tkGUI.ctrl.{type(self).__name__}")
        self.ctrl = ctrl

    def start(self):
        pass
    def stop(self):
        pass
    def reset(self):
        pass

    def draw_tb(self):
        pass
    def draw_cl(self):
        pass
