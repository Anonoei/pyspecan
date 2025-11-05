import matplotlib.pyplot as plt

from ...backend.mpl.plot import Plot

class CUIPlot:
    def __init__(self, parent, fig, plotter=Plot):
        self.parent = parent
        self.plotter = plotter(fig)

    @property
    def fig(self):
        return self.plotter.fig
    def ax(self, name):
        return self.plotter.ax(name)
    def add_ax(self, *args, **kwargs):
        return self.plotter.add_ax(*args,**kwargs)

class PSD(CUIPlot):
    def __init__(self, parent):
        fig = plt.figure(figsize=(5,5), layout="constrained")
        super().__init__(parent, fig)
        self.plotter.add_ax("psd", fig.add_subplot())

    def plot(self, freq, psd):
        self.ax("psd").ax.set_title("PSD")
        self.ax("psd").plot(freq, psd, name="psd", color="y")

    def show(self):
        self.plotter.fig.show()
