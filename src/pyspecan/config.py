from enum import Enum

class Mode(Enum):
    """Specan modes"""
    NONE = "none"
    SWEPT = "swept"
    RT = "rt"

    @classmethod
    def choices(cls):
        """return mode choices"""
        arr = []
        for inst in cls:
            if inst == cls.NONE:
                continue
            arr.append(inst.name)
        return arr

    @classmethod
    def get(cls, option: str):
        for inst in cls:
            if inst.name == option:
                return inst
        return cls.NONE

class View(Enum):
    """Specan views"""
    NONE = (("none",), None)
    CUI = (("c", "cui"), "cui")
    tkGUI = (("tk", "tkgui"), "tk_gui")

    @property
    def path(self):
        """return view import path name"""
        return self.value[1]

    @classmethod
    def get(cls, option: str):
        """return view instance"""
        for inst in cls:
            if inst.name == option or option in inst.value[0]:
                return inst
        return cls.NONE

    @classmethod
    def choices(cls):
        """return view choices"""
        arr = []
        for inst in cls:
            if inst == cls.NONE:
                continue
            for i in inst.value[0]:
                arr.append(i)
            arr.append(inst.name)
        return arr


class config:
    """Global variables for convenience"""
    __instance = None

    SENTINEL = object()
    MODE: Mode = Mode.NONE

    MON_MEM: bool = False
    PROFILE: bool = False
    PROFILE_PATH = [None, "pyspecan.prof"][1]

    def __new__(cls):
        if cls.__instance is None:
            cls.__instance = object.__new__(cls)
            cls.__instance._init()
        return cls.__instance

    def _init(self):
        pass
