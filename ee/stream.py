## `ee/stream.py`
"""
Entropy Engine streaming core
-----------------------------
Incremental, O(1)/tick Shannon entropy with EMA smoothing and first/second
numerical derivatives. Caller drives timing; we do not sleep.

Inputs are expected normalized to [0, 1]. If your source is not normalized,
you should preprocess it before passing to `stream_entropy`.
"""
from __future__ import annotations
import math
import collections
from typing import Iterable, Iterator, Dict

import numpy as np


def stream_entropy(
    sample_iter: Iterable[float],
    *,
    bins: int = 32,
    window: int = 256,
    dt: float = 0.05,       # seconds between successive samples (used for d/dt)
    ema: float = 0.20,      # EMA factor for H smoothing
) -> Iterator[Dict[str, float]]:
    """
    Yields dicts: {"t", "H", "Y", "Z"} per sample.

    - bins: number of histogram bins over [0,1]
    - window: sliding window length (in samples)
    - dt: sample interval (seconds) used for derivative scaling
    - ema: exponential smoothing factor applied to H

    Complexity per tick: O(1)
    """
    assert bins >= 2, "bins must be >= 2"
    assert window >= 2, "window must be >= 2"
    assert dt > 0, "dt must be > 0"
    assert 0.0 < ema <= 1.0, "ema must be in (0,1]"

    inv = float(bins)
    counts = np.zeros(bins, dtype=np.int32)
    ring = collections.deque(maxlen=window)
    logB = math.log(bins)
    eps = 1e-12

    H_s = None  # smoothed H~
    Y = 0.0
    t = 0.0

    for x in sample_iter:
        # Clamp input and compute bin index without searchsorted
        if x < 0.0:
            x = 0.0
        elif x > 1.0:
            x = 1.0
        bi = int(x * inv)
        if bi >= bins:
            bi = bins - 1

        # Incremental histogram update
        if len(ring) == window:
            old = ring.popleft()
            obi = int(min(bins - 1, max(0, int(old * inv))))
            counts[obi] -= 1
        ring.append(x)
        counts[bi] += 1

        N = int(counts.sum())
        if N <= 0:
            # No mass yet; yield zeros (rare with window>=2)
            H = 0.0
        else:
            p = counts / N
            H = -(p * np.log(p + eps)).sum() / logB  # normalized H~ in [0,1]

        H_prev = H_s
        Y_prev = Y
        H_s = H if H_prev is None else (ema * H + (1.0 - ema) * H_prev)
        Y = 0.0 if H_prev is None else (H_s - H_prev) / dt
        Z = 0.0 if H_prev is None else (Y - Y_prev) / dt

        t += dt
        yield {"t": float(t), "H": float(H_s), "Y": float(Y), "Z": float(Z)}