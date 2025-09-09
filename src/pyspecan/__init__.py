"""
pyspecan

A spectrum analyzer library

Github: https://github.com/Anonoei/pyspecan

PyPI: https://pypi.org/project/pyspecan/

This is intended to be used as a callable module (or a script), but can be used as a library
"""

__version__ = "0.2.2"
__author__ = "Anonoei <to+dev@an0.cx>"

from . import _internal

from .config import config, Mode, View
from . import err
from . import obj
from . import utils

from .model.model import Model

from .specan import SpecAn
