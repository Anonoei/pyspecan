import argparse

import numpy as np

from ...utils import args
from .mode import Mode, args_mode

from ...utils import psd as _psd

def args_swept(parser: argparse.ArgumentParser):
    mode = args.get_group(parser, "Mode (SWEPT)")
    args_mode(mode)

class ModeSwept(Mode):
    def __init__(self, model, **kwargs):
        super().__init__(model)
