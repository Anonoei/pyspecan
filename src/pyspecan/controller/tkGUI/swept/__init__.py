# freq plots
from .psd import PSD
from .spg import SPG
from .spg3d import SPG3D

# time plots
from .iq import IQ
from .pmf import PMF
from .iq3d import IQ3D

plots = {
    "PSD": PSD,
    "Spectrogram": SPG,
    # "SPG 3D": SPG3D,

    "IQ": IQ,
    "IQ 3D": IQ3D,
    "PMF": PMF,
}
