import numpy as np

from .window import WindowLUT
from .vbw import vbw as _vbw

def psd(samples, nfft=1024, overlap=0.8, Fs=1.0, vbw=None, win="blackman"):
    win_func = WindowLUT[win]
    overlap = 1-overlap
    n_samp = len(samples)
    n_frames = int(n_samp/(nfft*overlap))
    out = np.zeros((nfft, n_frames))

    # print(f"stft for {n_samp} samples / {out.shape[1]}*{nfft} FFT @ overlap {overlap}")

    for i in range(n_frames):
        s_idx = int(i*(nfft*overlap))
        e_idx = s_idx + nfft
        # print(f"snip {i} = [{s_idx}:{e_idx}]")
        if e_idx > n_samp:
            segment = np.zeros(nfft, dtype=samples.dtype)
            f_idx = n_samp-s_idx
            segment[:f_idx] = samples[s_idx:]
            # segment[f_idx:] = samples[-f_idx:]
        else:
            segment = samples[s_idx:e_idx]

        _psd = np.fft.fft(segment*win_func(nfft))
        _psd = np.abs(_psd)
        _psd = _psd**2 / (nfft*Fs)
        _psd = 10.0*np.log10(_psd)
        _psd = np.fft.fftshift(_psd)
        if vbw is not None:
            _psd = _vbw(_psd, vbw)
        out[:,i] = _psd
    return out
