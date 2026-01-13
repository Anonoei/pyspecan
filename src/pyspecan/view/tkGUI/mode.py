from ... import logger

def args_mode(parser):
    pass

class Mode:
    def __init__(self, view):
        self.log = logger.new(f"tkGUI.view.{type(self).__name__}")
        self.view = view

    def draw_tb(self, parent, col=0):
        return col
    def draw_cl(self, parent, row=0):
        return row

    def finish_tb(self):
        pass
    def finish_cl(self):
        pass
