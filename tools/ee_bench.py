## `tools/ee_bench.py`
"""
Enhanced micro-benchmark for ee.stream.stream_entropy
Measures per-tick compute time (no sleeps) and basic numeric sanity.

Run examples:
  python tools/ee_bench.py
  python tools/ee_bench.py --suite
  python tools/ee_bench.py --n 10000 --bins 32 --window 256 --csv
"""
from __future__ import annotations
import argparse
import time
import statistics as st
import numpy as np

from ee.stream import stream_entropy


def make_samples(n: int, seed: int = 0) -> np.ndarray:
    """Deterministic-ish test signal in [0,1] with small noise."""
    rng = np.random.default_rng(seed)
    x = 0.5
    out = np.empty(n, dtype=np.float64)
    for i in range(n):
        x += 0.02 * np.sin(i * 0.12) + 0.01 * np.sin(i * 0.031) + 0.005 * (rng.random() - 0.5)
        if x < 0.0:
            x = 0.0
        elif x > 1.0:
            x = 1.0
        out[i] = x
    return out


def bench(*, n: int = 5000, bins: int = 32, window: int = 256, dt: float = 0.05, ema: float = 0.2, warmup: int = 200) -> dict:
    """Return a dict of timing + basic numeric stats for given parameters."""
    samples = make_samples(n + warmup)

    # Warmup (fills caches and stabilizes arrays)
    for _ in stream_entropy(samples[:warmup], bins=bins, window=window, dt=dt, ema=ema):
        pass

    # Measure
    it = stream_entropy(samples[warmup:], bins=bins, window=window, dt=dt, ema=ema)
    t_prev = time.perf_counter_ns()
    times_ns = []
    Hvals = []
    Yvals = []
    Zvals = []
    count = 0
    for msg in it:
        now = time.perf_counter_ns()
        times_ns.append(now - t_prev)
        t_prev = now
        Hvals.append(msg["H"]) ; Yvals.append(msg["Y"]) ; Zvals.append(msg["Z"]) 
        count += 1
        if count >= n:
            break

    if not times_ns:
        return {}

    times_ms = np.asarray(times_ns, dtype=np.float64) / 1e6
    H = np.asarray(Hvals)
    Y = np.asarray(Yvals)
    Z = np.asarray(Zvals)

    stats = {
        "n": int(n),
        "bins": int(bins),
        "window": int(window),
        "dt": float(dt),
        "ema": float(ema),
        "mean_ms": float(times_ms.mean()),
        "median_ms": float(np.median(times_ms)),
        "p95_ms": float(np.percentile(times_ms, 95)),
        "p99_ms": float(np.percentile(times_ms, 99)),
        "min_ms": float(times_ms.min()),
        "max_ms": float(times_ms.max()),
        "ticks_per_sec_equiv": float(1000.0 / times_ms.mean()),
        "H_mean": float(np.mean(H)),
        "H_min": float(np.min(H)),
        "H_max": float(np.max(H)),
        "finite_ok": bool(np.isfinite(H).all() and np.isfinite(Y).all() and np.isfinite(Z).all()),
    }
    return stats


def main() -> None:
    ap = argparse.ArgumentParser(description="Benchmark stream_entropy per-tick cost (no sleeps).")
    ap.add_argument("--n", type=int, default=5000, help="ticks to measure (default 5000)")
    ap.add_argument("--bins", type=int, default=32)
    ap.add_argument("--window", type=int, default=256)
    ap.add_argument("--dt", type=float, default=0.05)
    ap.add_argument("--ema", type=float, default=0.2)
    ap.add_argument("--suite", action="store_true", help="run a small parameter sweep")
    ap.add_argument("--csv", action="store_true", help="CSV output")
    args = ap.parse_args()

    rows = []
    if args.suite:
        for b, w in [(16, 128), (32, 256), (32, 512), (64, 512)]:
            rows.append(bench(n=args.n, bins=b, window=w, dt=args.dt, ema=args.ema))
    else:
        rows.append(bench(n=args.n, bins=args.bins, window=args.window, dt=args.dt, ema=args.ema))

    if args.csv:
        keys = [
            "bins","window","n","dt","ema",
            "mean_ms","median_ms","p95_ms","p99_ms","min_ms","max_ms","ticks_per_sec_equiv",
            "H_mean","H_min","H_max","finite_ok",
        ]
        print(",".join(keys))
        for r in rows:
            print(",".join(str(r.get(k, "")) for k in keys))
    else:
        for r in rows:
            print(r)


if __name__ == "__main__":
    main()