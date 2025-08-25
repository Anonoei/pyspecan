class Manager:
    def __init__(self, root):
        self.root = root
        self.views = {}

    def add_view(self, view, settings=None):
        v = view(settings)
        self.views[view.__name__] = v
        return v

    def remove_view(self, view_name):
        if view_name in self.views:
            del self.views[view_name]
