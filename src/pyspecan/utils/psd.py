import numpy as np

from .window import WindowLUT
from .vbw import vbw as _vbw

def psd(samples, Fs=1.0, vbw=None, win="blackman"):
    N = len(samples)
    _psd = samples * WindowLUT[win](N)
    _psd = np.abs(np.fft.fft(_psd)) # type: ignore
    _psd = _psd**2 / (N*Fs)
    _psd = 10.0*np.log10(_psd)
    _psd = np.fft.fftshift(_psd)
    if vbw is not None:
        _psd = _vbw(_psd, vbw)
    return _psd
