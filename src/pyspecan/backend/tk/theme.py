"""tk themes"""
from ._theme import _Theme

class Light(_Theme):
    """pyspecan tk light theme"""
    C_FG = "#000000"
    C_FG_TEXT = "#000000"
    C_FG_ALT = C_FG
    C_FG_ACTIVE = C_FG
    C_FG_DISABLED = "#888888"
    C_FG_PRESSED = "#880000"
    C_FG_SELECTED = C_FG
    C_FG_FOCUS = C_FG
    C_FG_READONLY = "#444444"
    C_FG_INVALID = "#AA11AA"

    C_BG = "#EEEEEE"
    C_BG_TEXT = "#FFFFFF"
    C_BG_ALT = "#FFFFFF"
    C_BG_ACTIVE = "#DDDDDD"
    C_BG_DISABLED = "#CCCCCC"
    C_BG_PRESSED = "#AAAAAA"
    C_BG_SELECTED = C_BG
    C_BG_FOCUS = C_BG
    C_BG_READONLY = "#CCCCCC"
    C_BG_INVALID = C_BG

class Dark(_Theme):
    """pyspecan tk dark theme"""
    C_FG = "#FFFFFF"
    C_FG_TEXT = "#FFFFFF"
    C_FG_ALT = C_FG
    C_FG_ACTIVE = C_FG
    C_FG_DISABLED = "#888888"
    C_FG_PRESSED = "#FF8888"
    C_FG_SELECTED = C_FG
    C_FG_FOCUS = C_FG
    C_FG_READONLY = "#CCCCCC"
    C_FG_INVALID = "#AA11AA"

    C_BG = "#111111"
    C_BG_TEXT = "#222222"
    C_BG_ALT = "#000000"
    C_BG_ACTIVE = "#222222"
    C_BG_DISABLED = "#000000"
    C_BG_PRESSED = "#888888"
    C_BG_SELECTED = C_BG
    C_BG_FOCUS = C_BG
    C_BG_READONLY = "#333333"
    C_BG_INVALID = C_BG

theme = {
    "Light": Light,
    "Dark": Dark
}

def get(name: str) -> _Theme:
    return theme[name]
