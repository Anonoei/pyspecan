def args_sink(parser):
    pass

class Sink:
    def __init__(self, ctrl):
        self.ctrl = ctrl

    def start(self):
        pass
    def stop(self):
        pass
    def reset(self):
        pass

    def draw_tb(self):
        pass
    def draw_ctrl(self):
        pass
