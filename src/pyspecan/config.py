from enum import Enum

class Sink(Enum):
    """Sink modes, `value` is the command line name"""
    NONE = "none"
    FILE = "file"
    LIVE = "live"
    TCPIQ = "tcpiq"

    @classmethod
    def choices(cls) -> list[str]:
        """Command line names"""
        return [inst.value for inst in cls if inst != cls.NONE]

    @classmethod
    def get(cls, option) -> "Sink":
        """The sink named `option` (any case), NONE when there is none"""
        if isinstance(option, cls):
            return option
        option = str(option).lower()
        return next((inst for inst in cls if option in (inst.name.lower(), inst.value)), cls.NONE)

    @classmethod
    def normalize(cls, option: str) -> str:
        """argparse type: the command line name for `option`, unknown names pass through for argparse to reject"""
        inst = cls.get(option)
        return option if inst == cls.NONE else inst.value

class View(Enum):
    """Specan views: (names, the first is the command line one), import path"""
    NONE = (("none",), None)
    CUI = (("cui", "c"), "cui")
    tkGUI = (("tk", "tkgui"), "tk_gui")
    WEB = (("web", "w"), "web")

    @property
    def path(self):
        """return view import path name"""
        return self.value[1]

    @property
    def cli(self) -> str:
        return self.value[0][0]

    @classmethod
    def get(cls, option) -> "View":
        """The view named `option` (its name or an alias, any case), NONE when there is none"""
        if isinstance(option, cls):
            return option
        option = str(option).lower()
        return next((inst for inst in cls if option == inst.name.lower() or option in inst.value[0]), cls.NONE)

    @classmethod
    def choices(cls) -> list[str]:
        """Command line names"""
        return [inst.cli for inst in cls if inst != cls.NONE]

    @classmethod
    def normalize(cls, option: str) -> str:
        """argparse type: the command line name for `option`, unknown names pass through for argparse to reject"""
        inst = cls.get(option)
        return option if inst == cls.NONE else inst.cli


class config:
    """Global variables for convenience"""
    __instance = None

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
