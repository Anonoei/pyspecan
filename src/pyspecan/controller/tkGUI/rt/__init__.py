from .pst import PST
from .spg import SPG

from .iq import IQ
from .iq3d import IQ3D
from .pmf import PMF

plots = {
    "Persistent Histogram": PST,
    "Spectrogram": SPG,

    "IQ": IQ,
    "IQ 3D": IQ3D,
    "PMF": PMF
}
