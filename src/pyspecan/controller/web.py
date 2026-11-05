"""Create a web controller"""
from .WEB.base import Controller, args_ctrl

def GetController(sink):
    return Controller

def ControllerArgs(sink, parser):
    args_ctrl(parser)
