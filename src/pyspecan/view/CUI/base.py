"""Create a CUI view"""

from ..base import View as _View

class View(_View):
    """Parent CUI view class"""
    def __init__(self, **kwargs):
        self.running = True

    def mainloop(self):
        while self.running:
            try:
                self.menu()
            except KeyboardInterrupt:
                pass


    def menu(self):
        pass
