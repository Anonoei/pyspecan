import pyspecan

import numpy as np
import matplotlib as mpl
from matplotlib import cm
from matplotlib.colors import Normalize
import matplotlib.pyplot as plt
from mpl_toolkits.mplot3d import Axes3D

def main():
    path = "data/fm_rds_250k_1Msamples.iq"
    fmt = "cf32"
    Fs = 250000
    cf = 0
    nfft = 1024

    mode = pyspecan.Mode.SWEPT

    vbw = 1000
    window = "blackman"

    model = pyspecan.GetModel(mode)(path=path, fmt=fmt, nfft=nfft, Fs=Fs, cf=cf)
    psds = []
    while model.next():
        psd = model.psd(vbw, window)
        psds.append(psd)
        if len(psds) == 32:
            break

    fig = plt.figure(layout="tight")
    ax: Axes3D = fig.add_subplot(projection="3d")
    ax.set_box_aspect((3,6,3))
    # ax = fig.add_subplot()

    f = np.arange(0, nfft)
    t = np.arange(len(psds))
    x, y = np.meshgrid(f, t)

    psds = np.array(psds)

    # for i in t:
    #     ax.scatter(f, i, psds[i])

    # surf = ax.plot_surface(
    #     x, y, psds,
    #     linewidth=1,
    #     rstride=10, cstride=10,
    #     cmap="coolwarm", alpha=0.5,
    #     antialiased=False, shade=False, rasterized=True
    # )
    # surf.set_facecolor((1,1,1,1))

    # surf = ax.plot_surface(
    #     x, y, psds,
    #     cmap="viridis", alpha=0.5,
    #     rcount=1, ccount=nfft/8,
    #     antialiased=False, shade=False
    # )

    surf = ax.plot_wireframe(
        x, y, psds,
        rcount=0, ccount=64, alpha=0.5
    )

    # ax.contour(x, y, psds, zdir="x", offset=f[0])
    # ax.contour(x, y, psds, zdir='y', offset=len(psds))
    # ax.contour(x, y, psds, zdir="z", offset=np.min(psds))
    ax.contourf(x, y, psds, zdir="x", offset=f[0], cmap="coolwarm")
    ax.contourf(x, y, psds, zdir='y', offset=len(psds), cmap="coolwarm")
    ax.contourf(x, y, psds, zdir="z", offset=np.min(psds), cmap="coolwarm")

    # surf = ax.scatter(X, Y, Z)
    # surf = ax.plot_surface(f, t, psds)
    # surf = ax.plot_wireframe(X, Y, Z)
    # ax.plot_surface(f[:, None], t[None, :], psds)
    # ax.pcolormesh(x, y, z)

    plt.show()




if __name__ == "__main__":
    main()
