"""
pyspecan

A spectrum analyzer library

Github: https://github.com/Anonoei/pyspecan

PyPI: https://pypi.org/project/pyspecan/

This is intended to be used as a callable module (or a script), but can be used as a library
"""

__version__ = "0.6.2"
__author__ = "Anonoei <to+dev@an0.us>"

from . import _internal, err, obj, utils
from .config import View, config

# from .model.base import Model
from .model.base import Model
from .model.model import GetModel
from .specan import SpecAn
