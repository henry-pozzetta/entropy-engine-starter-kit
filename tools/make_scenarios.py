## `tools/make_scenarios.py`
"""
Generate three offline scenario tracks as JSONL under web/scenarios/.
Run once:
  python tools/make_scenarios.py
"""
from __future__ import annotations
import json
import math
import os
import random

OUTDIR = os.path.join("web", "scenarios")
os.makedirs(OUTDIR, exist_ok=True)


def write(name: str, seq):
    fp = os.path.join(OUTDIR, name)
    with open(fp, "w", encoding="utf-8") as f:
        for s in seq:
            f.write(json.dumps(s) + "\n")
    print("wrote", fp)


def mk_step_change(n=800):
    H = 0.3
    yph = 0.0
    out = []
    for i in range(n):
        if i == 300:
            H += 0.25  # step
        y = 0.05 * math.sin(yph)
        z = 0.12 * math.sin(yph * 0.7)
        yph += 0.12
        H = max(0, min(1, H + 0.02 * y + 0.5 * z * 0.05))
        out.append({"t": i * 0.05, "H": round(H, 4), "Y": round(y, 4), "Z": round(z, 4), "label": "step"})
    return out


def mk_bursts(n=800):
    H = 0.5
    out = []
    for i in range(n):
        if random.random() < 0.06:
            H = min(1, H + 0.1)
        H = max(0, H - 0.004)
        y = (H - 0.5) * 0.2
        z = (0.5 - H) * 0.15
        out.append({"t": i * 0.05, "H": round(H, 4), "Y": round(y, 4), "Z": round(z, 4), "label": "bursts"})
    return out


def mk_drift(n=800):
    H = 0.35
    out = []
    for i in range(n):
        H = min(1, H + 0.0009)
        y = 0.02
        z = 0.001
        out.append({"t": i * 0.05, "H": round(H, 4), "Y": round(y, 4), "Z": round(z, 4), "label": "drift"})
    return out


if __name__ == "__main__":
    write("step.jsonl", mk_step_change())
    write("bursts.jsonl", mk_bursts())
    write("drift.jsonl", mk_drift())