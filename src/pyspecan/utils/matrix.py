import numpy as np

def _fill(matrix):
    matrix = np.ascontiguousarray(matrix, dtype=np.int8)
    rows, cols = matrix.shape
    mask = matrix != 0

    s_idx = np.argmax(mask, axis=0)
    # e_idx = rows - 1 - np.argmax(mask[::-1], axis=0)
    e_idx = rows - 1 - np.argmax(np.flip(mask, axis=0), axis=0)

    # empty = mask.sum(axis=0) == 0
    empty = ~mask.any(axis=0)
    s_idx[empty] = 0
    e_idx[empty] = 0

    diff = np.zeros_like(matrix, dtype=np.int8)
    col_idx = np.arange(cols, dtype=np.int32)

    # s_rows = s_idx + 1
    # s_valid = s_rows < e_idx

    # e_rows = e_idx
    # e_valid = e_idx > s_idx
    # diff[s_rows[s_valid], col_idx[s_valid]] += 1
    # diff[e_rows[e_valid], col_idx[e_valid]] -= 1

    valid = s_idx < e_idx
    s_rows = s_idx[valid] + 1
    e_rows = e_idx[valid]

    np.add.at(diff, (s_rows, col_idx[valid]), 1)
    np.add.at(diff, (e_rows, col_idx[valid]), -1)

    np.cumsum(diff, axis=0, out=diff)
    matrix += diff

    # print(out)
    # exit()
    # for i in range(matrix.shape[1]):
    #     wh = np.where(matrix[:,i]>0)[0]
    #     matrix[np.min(wh):np.max(wh),i] += 1
    # matrix[np.min(matrix[:,None]):np.max(matrix[:,None]),None] += 1
    return matrix

def dot(x: int, y: int, psds, yt: float, yb: float):
    """Dot Matrix
    Each PSD's x/y mapped to histogram x/y
    """
    hist = np.zeros((y, x), dtype=np.int8)

    if np.all(psds < yb):
        return hist
    elif np.all(psds > yt):
        return hist

    y_rng = abs(abs(yt) - abs(yb))
    y_off = yb if yb > 0 else -yb

    x_ratio = x/psds.shape[0]
    y_ratio = y/y_rng

    x_idx = np.floor(np.arange(0, psds.shape[0])*x_ratio).astype(int)
    y_idx = np.floor((psds+y_off)*y_ratio).astype(int)

    y_idx = np.clip(y_idx, 0, y-1)

    y_val = np.ones_like(y_idx)
    y_val[y_idx == 0] = 0
    y_val[y_idx >= y-1] = 0

    for i in range(psds.shape[1]):
        hist[y_idx[:,i], x_idx] += y_val[:,i]
    return hist

def cdot(x, y, psds, yt=0.05, yb=0.05):
    hist = dot(x, y, psds, yt, yb)
    return _fill(hist)

def vec(x, y, psds, yt=0.05, yb=0.05, interp=32):
    """Vector Matrix
    Interpolate between PSD x/y to mimic vector matrix
    """
    y_int = np.zeros((psds.shape[0]*interp, psds.shape[1]))
    t = np.arange(psds.shape[0])*interp
    t_int = np.arange(psds.shape[0]*interp)-1
    for i in range(psds.shape[1]):
        y_int[:,i] = np.interp(t_int, t, psds[:,i])
    return dot(x, y, y_int, yt, yb)

def cvec(x, y, psds, yt=0.05, yb=0.05, interp=16):
    hist = vec(x, y, psds, yt, yb, interp)
    return _fill(hist)
