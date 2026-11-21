"""Configure matplotlib Style
"""
import matplotlib.style as mstyle

theme = {
    "Light": lambda: mstyle.use("default"),
    "Dark": lambda: mstyle.use("dark_background"),
}

def get(name: str):
    return theme[name]
