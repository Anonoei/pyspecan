from ... import logger

def args_mode(parser):
    pass

class Mode:
    def __init__(self, ctrl):
        self.log = logger.new(f"tkGUI.{type(self).__name__}")
        self.ctrl = ctrl

    def draw_tb(self):
        pass
    def draw_ctrl(self):
        pass
