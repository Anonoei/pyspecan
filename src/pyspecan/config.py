from enum import Enum

class Mode(Enum):
    NONE = "none"
    SWEPT = "swept"
    RT = "rt"

class config:
    __instance = None

    SENTINEL = object()
    MODE = Mode.NONE

    def __new__(cls):
        if cls.__instance is None:
            cls.__instance = object.__new__(cls)
            cls.__instance._init()
        return cls.__instance

    def _init(self):
        pass
