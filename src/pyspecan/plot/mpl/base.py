from matplotlib.figure import Figure
from matplotlib.axes import Axes
import matplotlib.pyplot as plt

plt.style.use('dark_background')

class Plot:
    """Generic plotting parent"""
    __slots__ = ("_fig", "_canv", "_axs")
    def __init__(self, fig: Figure = plt.figure()):
        if not fig.axes:
            fig.add_subplot()

        self._fig = fig
        self._canv = fig.canvas
        self._axs = fig.axes

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

    def ax(self, idx) -> Axes:
        return self._axs[idx]

    def art(self, i, j):
        raise NotImplementedError()

    def add_ax(self, *args, **kwargs):
        """Add new axes"""
        ax = self._fig.add_subplot(*args, **kwargs)
        self._axs.append(ax)

    def add_artist(self, idx, art, name):
        """Add artist to axis"""
        raise NotImplementedError()

    def plot(self, idx, *args, **kwargs):
        line, = self.ax(idx).plot(*args, **kwargs)
        return line

    def imshow(self, idx, *args, **kwargs):
        im = self.ax(idx).imshow(*args, **kwargs)
        return im

    def set_data(self, i,j, x, y):
        """Set axis i, artist j data"""
        raise NotImplementedError()

    def set_xdata(self, i, j, x):
        """Set axis i, artist j xdata"""
        raise NotImplementedError()

    def set_ydata(self, i, j, y):
        """set axis i, artist j ydata"""
        raise NotImplementedError()

    def set_xlim(self, idx, xmin, xmax):
        self.ax(idx).set_xlim(xmin, xmax)
    def set_ylim(self, idx, ymin, ymax):
        self.ax(idx).set_ylim(ymin, ymax)
    def relim(self, idx):
        self.ax(idx).relim()


class BlitPlot(Plot):
    """Plot supporting blitting"""
    __slots__ = ("_bg", "_art", "_cid")
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._bg = None
        self._art = []
        for _ in self._axs:
            self._art.append({})
        self._cid = self._canv.mpl_connect("draw_event", self._on_draw)

    def update(self):
        cv = self._canv
        if self._bg is None:
            self._on_draw(None)
        else:
            cv.restore_region(self._bg) # type: ignore
            self._draw_animated()
            cv.blit(self._fig.bbox)
        cv.flush_events()

    def art(self, i, j):
        return self._art[i].get(j, None)

    def add_artist(self, idx, art, name=None):
        if name is None:
            name = len(self._art[idx])
        if not art.figure == self._canv.figure:
            raise RuntimeError
        art.set_animated(True)
        self._art[idx][name] = art

    def add_ax(self, *args, **kwargs):
        super().add_ax(*args, **kwargs)
        self._art.append({})

    def plot(self, idx, *args, **kwargs):
        name = kwargs.get("name", None)
        if name is not None:
            del kwargs["name"]
        if self.art(idx, name) is None:
            line = super().plot(idx, *args, **kwargs)
            self.add_artist(idx, line, name)
        else:
            line = self.art(idx, name)
            if len(args) == 2:
                line.set_data(*args)
            else:
                print(f"plot args: {len(args)}")
                print(f"plot kwargs: {kwargs}")
        return line

    def imshow(self, idx, *args, **kwargs):
        name = kwargs.get("name", None)
        if name is not None:
            del kwargs["name"]
        if self.art(idx, name) is None:
            im = super().imshow(idx, *args, **kwargs)
            self.add_artist(idx, im, name)
        else:
            im = self.art(idx, name)
            im.set_data(*args)
            for k, v in kwargs.items():
                if k in ("cmap", "interpolation", "resample", "rasterized"):
                    im.set(**{k: v})
        return im

    def set_data(self, i,j, x, y):
        self.art(i,j).set_data(x,y)

    def set_xdata(self, i, j, x):
        self.art(i,j).set_xdata(x)

    def set_ydata(self, i, j, y):
        self.art(i,j).set_ydata(y)

    def set_xlim(self, idx, xmin, xmax):
        super().set_xlim(idx, xmin, xmax)
        self.relim(idx)
    def set_ylim(self, idx, ymin, ymax):
        super().set_ylim(idx, ymin, ymax)
        self.relim(idx)
    def relim(self, idx):
        super().relim(idx)
        self.canvas.draw()

    def _on_draw(self, event):
        cv = self._canv
        if event is not None:
            if event.canvas != cv:
                raise RuntimeError
        self._bg = cv.copy_from_bbox(cv.figure.bbox) # type: ignore
        self._draw_animated()

    def _draw_animated(self):
        for ax in self._art:
            for art in ax.values():
                self._fig.draw_artist(art)
