"""Configure matplotlib Style
"""
import matplotlib.pyplot as plt

theme = {
    "Light": lambda: plt.style.use("default"),
    "Dark": lambda: plt.style.use("dark_background"),
}

def get(name: str):
    return theme[name]
