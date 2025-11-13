import pyspecan

import matplotlib.pyplot as plt

def main():
    path = "data/fm_rds_250k_1Msamples.iq"
    fmt = "cf32"
    Fs = 250000
    # path = ["data/BPSK_2SPS.sigmf-data", "data/QPSK_2SPS.sigmf-data"][1]
    # fmt = "cf32"
    # Fs = 1000000

    cf = 0
    nfft = 1024

    mode = pyspecan.Mode.SWEPT

    vbw = 1000
    window = "blackman"

    model = pyspecan.GetModel(mode)(path=path, fmt=fmt, nfft=nfft, Fs=Fs, cf=cf)

    pmf = pyspecan.utils.ComplexPMF(256)
    # pmf = PMF(256)

    fig, axs = plt.subplots(1,2, sharey=True, width_ratios=(0.8,0.2), layout="constrained")
    axs[1].locator_params(axis="x", nbins=5)

    while model.next():
        samples = model.samples
        pmf.update(samples)
        # print(f"mean: {pmf.mean():.3f} | std: {pmf.std():.3f}")

        # x = pmf.x
        # y = pmf.y

        # axs[0].plot(samples.real)
        # axs[0].plot(samples.imag)
        # axs[1].plot(y.real, x.real)
        # axs[1].plot(y.imag, x.imag)
        # fig.suptitle(pmf.num)
        # plt.pause(0.1)
        # axs[0].cla()
        # axs[1].cla()

        # axs[1].plot(x.real, y.real)
        # axs[1].plot(x.imag, y.imag)

    x = pmf.x
    y = pmf.y
    axs[0].plot(samples.real)
    axs[0].plot(samples.imag)
    axs[0].set_ylim(pmf.x_lim)
    # axs[1].plot(x.real, y.real)
    axs[1].plot(y.real, x.real)
    axs[1].plot(y.imag, x.imag)
    # axs[1].plot(x.imag, y.imag)
    plt.show()

if __name__ == "__main__":
    main()
