from matplotlib.figure import Figure
from matplotlib.axes import Axes
import matplotlib.pyplot as plt

from .ax import Ax, BlitAx

# plt.style.use('dark_background')

class _Plot:
    """Generic plotting parent"""
    __slots__ = ("_fig", "_canv", "_axs")
    def __init__(self, fig: Figure = plt.figure()):
        self._fig = fig
        self._canv = fig.canvas
        self._axs = {}

    def show(self):
        print(f"axs: {self._axs}")

    def update(self):
        """Update plot"""
        self._canv.draw()

    @property
    def fig(self):
        return self._fig

    @property
    def canvas(self):
        return self._canv

    def ax(self, name) -> Ax:
        return self._axs[name]

    def axes(self):
        return [v for v in self._axs.values()]

    def add_ax(self, name, ax: Axes):
        """Add new axes"""
        self._axs[name] = Ax(ax)

    def cla(self, name=None):
        if name is None:
            for xname, ax in self._axs.items():
                ax.cla()
        else:
            self.ax(name).cla()

class Plot(_Plot):
    def __init__(self, fig: Figure = plt.figure()):
        super().__init__(fig)
        for i, ax in enumerate(fig.axes):
            self._axs[i] = Ax(ax, self)

class BlitPlot(_Plot):
    """Plot supporting blitting"""
    __slots__ = ("_bg", "_cid")
    def __init__(self, fig: Figure = plt.figure()):
        super().__init__(fig)
        for i, ax in enumerate(fig.axes):
            self._axs[i] = BlitAx(ax, self)
        self._bg = None
        self._cid = self._canv.mpl_connect("draw_event", self._on_draw)

    def update(self):
        cv = self.canvas
        fig = cv.figure
        if self._bg is None:
            self._on_draw(None)
        else:
            cv.restore_region(self._bg) # type: ignore
            self._draw_animated()
            # cv.blit(self._fig.bbox)
            cv.blit(fig.bbox)
        cv.flush_events()

    def add_ax(self, name, ax: Axes):
        self._axs[name] = BlitAx(ax)

    def _on_draw(self, event):
        cv = self.canvas
        if event is not None:
            if event.canvas != cv:
                raise RuntimeError
        self._bg = cv.copy_from_bbox(cv.figure.bbox) # type: ignore
        self._draw_animated()

    def _draw_animated(self):
        for xname, ax in self._axs.items():
            for aname, art in ax.artists.items():
                # print(f"Drawing {xname}[{aname}]")
                self._fig.draw_artist(art)
