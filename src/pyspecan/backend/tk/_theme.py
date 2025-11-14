"""Configure ttk Style

TButton
TCheckbutton
TCombobox
TEntry
TFrame
TLabel
TLabelFrame
TMenubutton
TNotebook
TPanedwindow
Horizontal.TProgressbar
Vertical.TProgressbar
TRadiobutton
TScale
    Horizontal.TScale
    Vertical.TScale
TScrollbar
    Horizontal.TScrollbar
    Vertical.TScrollbar
TSeparator
TSizegrip
Treeview
"""
import tkinter as tk
from tkinter import ttk

def _print(style=None):
    if style is None:
        style = ttk.Style()
    print(style.theme_use(None))
    for element in ("TCheckbutton",):
        print(f"{element}:", end="")
        print(f" CONFIG {style.configure(element)} |", end="")
        print(f" MAP {style.map(element)} |", end="")
        print(f" LAYOUT {style.layout(element)} |", end="")
        print()
    exit()

class _Theme:
    """pyspecan theme"""
    _style: ttk.Style = None # type: ignore

    C_FG = "#FF00FF"
    C_FG_TEXT = C_FG
    C_FG_ALT = C_FG
    C_FG_ACTIVE = C_FG
    C_FG_DISABLED = C_FG
    C_FG_PRESSED = C_FG
    C_FG_SELECTED = C_FG
    C_FG_FOCUS = C_FG
    C_FG_READONLY = C_FG
    C_FG_INVALID = C_FG

    C_BG = "#00FF00"
    C_BG_TEXT = C_BG
    C_BG_ALT = C_BG
    C_BG_ACTIVE = C_BG
    C_BG_DISABLED = C_BG
    C_BG_PRESSED = C_BG
    C_BG_SELECTED = C_BG
    C_BG_FOCUS = C_BG
    C_BG_READONLY = C_BG
    C_BG_INVALID = C_BG

    def __new__(cls, parent):
        if cls._style is None:
            cls._style = ttk.Style(parent)
        # _print(cls._style)

        name = f"pyspecan.{cls.__name__}"

        try:
            cls._style.theme_create(name, "classic")
            cls._style.theme_use(name)
            cls._style.configure(".", font=("TKDefaultFont", 10))
            cls._config_base()
            cls._config()
        except tk.TclError: # The theme already exists
            cls._style.theme_use(name)
        # _print(cls._style)


    @classmethod
    def _config_base(cls):
        style = {
            "TButton": {
                "relief": "raised",
                "padding": (5,2),
                "anchor": "center",
                "justify": "center"
            },
            "Settings.TButton": {
                "font": ("TkDefaultFont", 6),
                "padding": (5,0)
            },
            "Close.TButton": {
                "font": ("TkDefaultFont", 6),
                "padding": (5,0)
            },
            "AddRow.TButton": {
                "font": ("TkDefaultFont", 7),
                "padding": (5,0)
            },
            "AddCol.TButton": {
                "font": ("TkDefaultFont", 7),
                "padding": (5,0)
            },
            "Toggle.TButton": {
                "font": ("TkDefaultFont", 7),
                "padding": (5,0),
                "highlightthickness": 0,
                "focusthickness": 0,
            },
            "Time.TLabel": {
                "font": ("TkDefaultFont", 8),
            }
        }
        cls.configure(style)
        maps = {
            "TButton": {
                "relief": [
                    ('disabled', 'flat')
                ]
            }
        }
        cls.map(maps)

    @classmethod
    def _config(cls):
        default_style = {
            "foreground": cls.C_FG,
            "selectforeground": cls.C_FG_TEXT,
            "fieldforeground": cls.C_FG_TEXT,
            "indicatorcolor": cls.C_FG,
            "background": cls.C_BG,
            "selectbackground": cls.C_BG_PRESSED,
            "fieldbackground": cls.C_BG_TEXT,
            "troughcolor": cls.C_BG_TEXT,
        }
        cls._style.configure(".", **default_style)
        default_maps = {
            "foreground": [
                ('active', cls.C_FG_ACTIVE),
                ('disabled', cls.C_FG_DISABLED),
            ],
            "background": [
                ('active', cls.C_BG_ACTIVE),
                ('disabled', cls.C_BG_DISABLED),
            ],
        }
        cls._style.map(".", **default_maps) # type: ignore
        style = {
            "TEntry": {
                "background": cls.C_BG_TEXT,
            },
            "TCheckbutton": {
                "indicatorcolor": cls.C_BG, # color when off
            },
        }
        cls.configure(style)
        maps = {
            "TButton": {
                "foreground":[
                    ('pressed', cls.C_FG_PRESSED),
                    ('disabled', cls.C_FG_DISABLED),
                ],
                "background": [
                    ('pressed', '!disabled', cls.C_BG_PRESSED),
                ]
            },
            "TEntry": {
                "fieldforeground": [
                    ('readonly', cls.C_FG_READONLY),
                    ('disabled', cls.C_FG_READONLY),
                ],
                "fieldbackground": [
                    ('readonly', cls.C_BG_READONLY),
                    ('disabled', cls.C_BG_READONLY),
                ],
            },
            "TCheckbutton": {
                "indicatorcolor": [
                    ("selected", cls.C_FG_PRESSED) # color when on
                ]
            }
        }
        cls.map(maps)

    @classmethod
    def configure(cls, obj, show=False):
        for k, v in obj.items():
            if not v:
                continue
            # if show:
            #     print(f"Configuring {k}, {v}")
            cls._style.configure(k, **v)
    @classmethod
    def map(cls, obj, show=False):
        for k, v in obj.items():
            if not v:
                continue
            # if show:
            #     print(f"Mapping {k}, {v}")
            cls._style.map(k, **v)
