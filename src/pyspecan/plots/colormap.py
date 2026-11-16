"""Colormaps as plain numpy lookup tables, shared by every renderer"""
import numpy as np

# name -> ((position, (r, g, b)), ...) with channels in 0..1
STOPS: dict[str, tuple] = {
    "magma": tuple((i/8, tuple(c/255 for c in rgb)) for i, rgb in enumerate((
        (0, 0, 4), (28, 16, 68), (79, 18, 123), (129, 37, 129), (181, 54, 122),
        (229, 80, 100), (251, 135, 97), (254, 194, 135), (252, 253, 191)))),
    # black -> deep blue -> teal -> green -> amber -> red -> warm white. Many muted stops, so levels read
    # as a smooth heat gradient and the dim end (the ghost, the noise skirts) stays in the blues
    "hot": (
        (0.00, (0.00, 0.00, 0.00)),
        (0.07, (0.02, 0.02, 0.17)),
        (0.20, (0.05, 0.10, 0.45)),
        (0.34, (0.07, 0.30, 0.66)),
        (0.46, (0.10, 0.52, 0.66)),
        (0.58, (0.25, 0.65, 0.45)),
        (0.69, (0.62, 0.74, 0.25)),
        (0.79, (0.92, 0.72, 0.18)),
        (0.89, (0.92, 0.42, 0.14)),
        (0.96, (0.84, 0.18, 0.14)),
        (1.00, (0.98, 0.88, 0.80)),
    ),
    "cold": (
        (0.00, (0.0, 0.0, 0.0)),
        (0.01, (0.1, 0.0, 0.0)),
        (0.20, (0.2, 0.0, 0.0)),
        (0.50, (0.0, 0.8, 0.5)),
        (1.00, (0.0, 0.0, 1.0)),
    ),
    "radar": (
        (0.00, (0.0, 0.0, 0.0)),
        (0.05, (0.0, 0.1, 0.0)),
        (0.50, (0.2, 0.8, 0.2)),
        (1.00, (1.0, 1.0, 1.0)),
    ),
    "grey": (
        (0.00, (0.0, 0.0, 0.0)),
        (0.50, (0.5, 0.5, 0.5)),
        (1.00, (1.0, 1.0, 1.0)),
    ),
}

def names() -> list[str]:
    return list(STOPS)

def lut(name: str, size=256) -> np.ndarray:
    """(size, 3) uint8 lookup table"""
    stops = STOPS[name]
    pos = [p for p, _ in stops]
    x = np.linspace(0.0, 1.0, size)
    chans = [np.interp(x, pos, [c[i] for _, c in stops]) for i in range(3)]
    return np.round(np.stack(chans, axis=1) * 255).astype(np.uint8)
