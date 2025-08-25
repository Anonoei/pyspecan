"""
pyspecan

A spectrum analyzer library

Github: https://github.com/Anonoei/pyspecan

PyPI: https://pypi.org/project/pyspecan/
"""

__version__ = "0.1.0"
__author__ = "Anonoei <to+dev@an0.cx>"

from .config import config
from . import err
from . import obj
from . import utils

from .model.model import Model

from .specan import SpecAn
