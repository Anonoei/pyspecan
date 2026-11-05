from ... import logger

def args_sink(parser):
    pass

class Sink:
    """tkGUI controller for a model sink"""
    def __init__(self, ctrl):
        self.log = logger.new(f"tkGUI.ctrl.{type(self).__name__}")
        self.ctrl = ctrl

    def start(self):
        self.ctrl.run_command("start")

    def stop(self):
        self.ctrl.run_command("stop")

    def reset(self):
        self.ctrl.run_command("reset")

    def draw_tb(self, status: dict):
        """Update the toolbar from the playback status"""
    def draw_cl(self):
        """Update the control panel from the model"""
