"""Initialize CUI Controller"""
from .CUI.base import Controller, define_args

def GetController(mode):
    return Controller

def ControllerArgs(mode):
    return define_args
