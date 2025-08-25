import numpy as np

WindowLUT = {
    "rect": np.ones,
    "blackman": np.blackman,
    "hanning": np.hanning,
    "hamming": np.hamming,
}
