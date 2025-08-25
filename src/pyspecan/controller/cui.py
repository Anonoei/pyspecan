
from ..utils import dialog

from ..model.model import Model
from ..model.reader import Format
from ..view.cui import CUI

class Controller:
    def __init__(self, model: Model, view: CUI):
        self.model = model
        self.view = view
