"""matplotlib colormaps built from the shared plots.colormap tables"""
from matplotlib.colors import ListedColormap

from ...plots import colormap

cmap = {name: ListedColormap(colormap.lut(name) / 255.0, name=f"pyspecan-{name}") for name in colormap.names()}
