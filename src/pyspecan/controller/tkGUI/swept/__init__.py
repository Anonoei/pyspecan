# freq plots
from .psd import PSD
from .spg import SPG
from .spg3d import SPG3D
from .freq import Freq

# time plots
from ..shared.iq import IQ
from ..shared.pmf import PMF
from ..shared.iq3d import IQ3D
from ..shared.phasor import Phasor

plots = {
    "PSD": PSD,
    "Spectrogram": SPG,
    # "SPG 3D": SPG3D,
    "FFT": Freq,

    "IQ": IQ,
    "IQ 3D": IQ3D,
    "PMF": PMF,
    "Phasor": Phasor
}
