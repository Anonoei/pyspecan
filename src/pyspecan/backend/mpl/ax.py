from matplotlib.axes import Axes

class Ax:
    def __init__(self, ax: Axes, parent=None):
        self.parent = parent
        self.ax = ax
        self._art = {}
        for i, art in enumerate(ax.artists):
            self.add_artist(i, art)

    @property
    def fig(self):
        return self.ax.figure

    @property
    def canvas(self):
        return self.fig.canvas

    @property
    def artists(self):
        return self._art

    def art(self, name):
        return self._art.get(name, None)

    def add_artist(self, name, art):
        if not art.figure == self.canvas.figure:
            raise RuntimeError
        art.set_animated(True)
        art.set_visible(True)
        self._art[name] = art

    def plot(self, *args, **kwargs):
        name = kwargs.get("name", None)
        if name is not None:
            del kwargs["name"]
        else:
            name = len(self._art)
        if self.art(name) is None:
            line, = self.ax.plot(*args, **kwargs)
            self.add_artist(name, line)
        else:
            line = self.art(name)
            if len(args) == 2:
                line.set_data(*args) # type: ignore
            else:
                print(f"plot args: {len(args)}")
                print(f"plot kwargs: {kwargs}")
        return line

    def plot3d(self, *args, **kwargs):
        name = kwargs.get("name", None)
        if name is not None:
            del kwargs["name"]
        else:
            name = len(self._art)
        if self.art(name) is None:
            line, = self.ax.plot(*args, **kwargs)
            self.add_artist(name, line)
        else:
            line = self.art(name)
            if len(args) == 3:
                line.set_data_3d(*args) # type: ignore
            else:
                print(f"plot args: {len(args)}")
                print(f"plot kwargs: {kwargs}")
        return line

    def scatter(self, *args, **kwargs):
        name = kwargs.get("name", None)
        if name is not None:
            del kwargs["name"]
        else:
            name = len(self._art)
        if self.art(name) is None:
            line, = self.ax.plot(*args, **kwargs)
            self.add_artist(name, line)
        else:
            line = self.art(name)
            if len(args) == 2:
                line.set_data(*args) # type: ignore
            else:
                print(f"plot args: {len(args)}")
                print(f"plot kwargs: {kwargs}")
        return line

    def imshow(self, *args, **kwargs):
        name = kwargs.get("name", None)
        if name is not None:
            del kwargs["name"]
        else:
            name = len(self._art)
        if self.art(name) is None:
            im = self.ax.imshow(*args, **kwargs)
            self.add_artist(name, im)
        else:
            im = self.art(name)
            im.set_data(*args) # type: ignore
            ks = [k for k in kwargs.keys()]
            for k in ks:
                if k in ("cmap", "interpolation", "resample", "rasterized"):
                    im.set(**{k: kwargs[k]}) # type: ignore
                    del kwargs[k]
        return im

    def plot_wireframe(self, *args, **kwargs):
        name = kwargs.get("name", None)
        if name is not None:
            del kwargs["name"]
        else:
            name = len(self._art)
        surf = self.ax.plot_wireframe(*args, **kwargs) # type: ignore
        # self.add_artist(name, surf)
        return surf

    def plot_surface(self, *args, **kwargs):
        name = kwargs.get("name", None)
        if name is not None:
            del kwargs["name"]
        else:
            name = len(self._art)
        surf = self.ax.plot_surface(*args, **kwargs) # type: ignore
        # self.add_artist(name, surf)
        return surf

    def set_data(self, name, *args):
        self.art(name).set_data(*args) # type: ignore

    def set_xdata(self, name, x):
        self.art(name).set_xdata(x) # type: ignore

    def set_ydata(self, name, y):
        self.art(name).set_ydata(y) # type: ignore

    def set_xlim(self, xmin, xmax):
        self.ax.set_xlim(xmin, xmax)
    def set_ylim(self, ymin, ymax):
        self.ax.set_ylim(ymin, ymax)

    def relim(self):
        self.ax.relim()

    def cla(self):
        self.ax.cla()

class BlitAx(Ax):
    def set_xlim(self, *args, **kwargs):
        super().set_xlim(*args, **kwargs)
        self.relim()

    def set_ylim(self, *args, **kwargs):
        super().set_ylim(*args, **kwargs)
        self.relim()

    def relim(self, *args, **kwargs):
        super().relim(*args, **kwargs)
        self.canvas.draw()
