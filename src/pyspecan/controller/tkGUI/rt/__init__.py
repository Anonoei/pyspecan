from .pst import PST
from .spg import SPG

# time plots
from ..shared.iq import IQ
from ..shared.pmf import PMF
from ..shared.iq3d import IQ3D
from ..shared.phasor import Phasor

plots = {
    "Persistent Histogram": PST,
    "Spectrogram": SPG,

    "IQ": IQ,
    "IQ 3D": IQ3D,
    "PMF": PMF,
    "Phasor": Phasor
}
