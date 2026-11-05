from .psd import PSD
from .spg import SPG
from .fft import FFT
from .shared import IQ, PMF, Phasor

# names shown in the browser's plot picker
plots = {
    "PSD": PSD,
    "Spectrogram": SPG,
    "FFT": FFT,
    "IQ": IQ,
    "PMF": PMF,
    "Phasor": Phasor,
}
