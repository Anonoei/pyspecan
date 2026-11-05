import numpy as np

def sigma2fwhm(sigma):
    return sigma * np.sqrt(8 * np.log(2))

def fwhm2sigma(fwhm):
    return fwhm / np.sqrt(8 * np.log(2))

def gaussian(y, sigma):
    fwhm = sigma2fwhm(sigma)
    x = np.arange(-int(sigma)*4, int(sigma)*4+1)

    kernel = np.exp(-(x) ** 2 / (2 * sigma ** 2))

    kernel_above_thresh = kernel > 0.0001
    finite_kernel = kernel[kernel_above_thresh]
    finite_kernel = finite_kernel / finite_kernel.sum()

    kernel_n_below_0 = int((len(finite_kernel) - 1) / 2.)

    smi = int(fwhm)
    smin = np.min(y)
    ex_samps = np.concatenate((np.repeat(smin, smi), y, np.repeat(smin, smi)))
    convolved_y = np.convolve(ex_samps, finite_kernel)
    smoothed_by_convolving = convolved_y[kernel_n_below_0+smi:(len(y)+kernel_n_below_0+smi)]
    return smoothed_by_convolving

def vbw(psd, smooth):
    return gaussian(psd, fwhm2sigma(smooth))

def vbw_rows(psd, smooth):
    """`vbw` applied to every row of a (rows, n) array at once"""
    psd = np.asarray(psd, dtype=np.float64)
    if psd.ndim == 1:
        return vbw_rows(psd[None, :], smooth)[0]
    sigma = fwhm2sigma(smooth)
    x = np.arange(-int(sigma)*4, int(sigma)*4+1)
    kernel = np.exp(-(x) ** 2 / (2 * sigma ** 2))
    kernel = kernel[kernel > 0.0001]
    kernel = kernel / kernel.sum()
    k_below = int((len(kernel) - 1) / 2.)

    rows, n = psd.shape
    smi = int(sigma2fwhm(sigma))
    pad = np.broadcast_to(psd.min(axis=1, keepdims=True), (rows, smi))
    ext = np.concatenate((pad, psd, pad), axis=1)

    size = 1 << int(np.ceil(np.log2(ext.shape[1] + len(kernel) - 1)))
    conv = np.fft.irfft(np.fft.rfft(ext, size, axis=1) * np.fft.rfft(kernel, size), size, axis=1)
    return conv[:, k_below+smi:n+k_below+smi]
