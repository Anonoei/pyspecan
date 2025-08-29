"""Initialize View base class"""
class View:
    """Parent view class"""
    __slots__ = ("view",)
    def __init__(self, view):
        self.view = view

    def mainloop(self):
        """Initialize the view"""

    def quit(self):
        """Gracefully exit"""
