"""Initialize Controller base class"""
from ..model.model import Model
from ..view.base import View as _View

class Controller:
    """Parent controller class"""
    __slots__ = ("model", "view")
    def __init__(self, model: Model, view: _View):
        self.model: Model = model
        self.view = view
