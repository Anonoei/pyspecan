"""Initialize CUI Controller"""
from .base import Controller as _Controller

from ..view.cui import View as CUI
from ..model.model import Model

class Controller(_Controller):
    """CUI Controller"""
    def __init__(self, model: Model, view: CUI):
        super().__init__(model, view)
        self.view: CUI = self.view # type hints
