#!/usr/bin/env python3
"""
Entropy Engine MVP (single-file, with visual scaling flags)
- Clock-driven ingestion from: random | csv | tcp | module (test_stream_gen.Generator)
- Rolling-window normalized entropy H~ in [0,1], plus derivatives Y (slope) and Z (curvature)
- EeFrame JSON emission per tick
- Dash 3D UI showing (H~, Y, Z) arrow, history trail, and latest frame
- NEW: --viz_y_gain, --viz_z_gain (plot-only scaling), --viz_aspect (x,y,z)

Run examples:
  # TCP (pair with generator)
  python ee_mvp.py --source tcp --tcp_host 127.0.0.1 --tcp_port 9009 --dt 0.25 --bins 24 --window 180 --viz_y_gain 1.5 --viz_z_gain 3 --viz_aspect 1,1,1.6

  # Module (in-process)
  python ee_mvp.py --source module --datatype 123 --uf 0.2 --seed 42 --dt 1.0 --bins 24 --window 180 --viz_z_gain 3
"""

from __future__ import annotations
import argparse, collections, dataclasses, hashlib, json, math, os, random, socket, sys, time
from typing import Deque, Optional, Tuple

import numpy as np
import pandas as pd

# Dash / Plotly
from dash import Dash, dcc, html, Input, Output
import plotly.graph_objects as go


# =========================
# Args
# =========================

def build_arg_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser("Entropy Engine MVP")

    ap.add_argument("--source", choices=["random", "csv", "tcp", "module"], default="random",
                    help="Input source for the telemetry stream.")
    # CSV
    ap.add_argument("--path", type=str, default="telemetry.csv",
                    help="CSV path when --source=csv (expects header 'value').")
    ap.add_argument("--loop", action="store_true", default=True,
                    help="Loop CSV when end reached (default True).")

    # TCP
    ap.add_argument("--tcp_host", type=str, default="127.0.0.1")
    ap.add_argument("--tcp_port", type=int, default=9009)

    # Module (test_stream_gen)
    ap.add_argument("--datatype", type=str, default="123", help="123|abc|sym|mix (module mode)")
    ap.add_argument("--uf", type=float, default=0.2, help="Unexpected factor [0..1] (module mode)")
    ap.add_argument("--seed", type=int, default=42)

    # Engine timing / entropy config
    ap.add_argument("--dt", type=float, default=0.25, help="Tick interval in seconds.")
    ap.add_argument("--bins", type=int, default=24, help="Histogram bins for numeric entropy.")
    ap.add_argument("--window", type=int, default=180, help="Rolling window length (number of samples).")
    ap.add_argument("--Tstar", type=float, default=30.0, help="Slope/curvature time scaling.")

    # UI / server
    ap.add_argument("--host", type=str, default="127.0.0.1")
    ap.add_argument("--port", type=int, default=8050)

    # ---- NEW: visualization-only scaling flags ----
    ap.add_argument("--viz_y_gain", type=float, default=1.0, help="Plot-only scale multiplier for Y (slope).")
    ap.add_argument("--viz_z_gain", type=float, default=2.0, help="Plot-only scale multiplier for Z (curvature).")
    ap.add_argument("--viz_aspect", type=str, default="1,1,1",
                    help="Plotly 3D aspect ratio as 'x,y,z' (e.g., '1,1,1.6' to give Z more depth).")

    return ap


# =========================
# Sources
# =========================

class CsvSource:
    def __init__(self, path: str, loop: bool = True):
        if not os.path.exists(path):
            raise FileNotFoundError(f"CSV not found: {path}")
        df = pd.read_csv(path)
        if "value" not in df.columns:
            raise ValueError("CSV must have a 'value' header.")
        self.values = df["value"].astype(float).values
        if len(self.values) == 0:
            raise ValueError("CSV has no rows under 'value'.")
        self.loop = loop
        self.i = 0

    def next(self) -> float:
        v = float(self.values[self.i])
        self.i += 1
        if self.i >= len(self.values):
            if self.loop:
                self.i = 0
            else:
                self.i = len(self.values) - 1  # hold last
        return v


class TcpSource:
    """
    Connects to a local generator that sends one value per line:
      - plain: '0.123\\n'
      - json:  '{"value": 0.123}\\n'
    Latest value is sample-and-held if no new data arrives between ticks.
    """
    def __init__(self, host="127.0.0.1", port=9009, default=0.0):
        self.addr = (host, port)
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.sock.settimeout(5.0)
        self.sock.connect(self.addr)
        self.sock.settimeout(0.0)  # non-blocking
        self.buf = b""
        self.latest = float(default)

    def _try_read(self):
        try:
            chunk = self.sock.recv(4096)
            if not chunk:
                return
            self.buf += chunk
            while b"\n" in self.buf:
                line, self.buf = self.buf.split(b"\n", 1)
                s = line.strip().decode("utf-8")
                if not s:
                    continue
                try:
                    if s.startswith("{"):
                        obj = json.loads(s)
                        self.latest = float(obj.get("value"))
                    else:
                        self.latest = float(s)
                except Exception:
                    # ignore malformed lines
                    pass
        except BlockingIOError:
            pass
        except Exception:
            # transient errors → hold previous
            pass

    def next(self) -> float:
        self._try_read()
        return float(self.latest)


class ModuleSource:
    """
    In-process plugin using test_stream_gen.Generator (module mode).
    If it returns a string token (abc/sym/mix), encode to a stable float in [-1,1]
    so the numeric entropy path works without changing internals.
    """
    def __init__(self, datatype="123", uf=0.2, seed=42, dt=1.0):
        import test_stream_gen as tsg
        cfg = tsg.StreamConfig(datatype=datatype, clock=dt, runtime=0, uf=uf, seed=seed,
                               mode="module", dt_for_module=dt)
        self.gen = tsg.Generator(cfg)
        self.step = 0

    @staticmethod
    def _encode_token(token: str) -> float:
        h = hashlib.blake2b(token.encode(), digest_size=8).digest()
        u = int.from_bytes(h, "little") / 2**64  # [0,1)
        return 2.0*u - 1.0  # map to [-1,1]

    def next(self) -> float:
        v = self.gen.next_for_module(self.step)
        self.step += 1
        if isinstance(v, str):
            return self._encode_token(v)
        return float(v)


class RandomWalkSource:
    def __init__(self, drift=0.0, noise=0.1):
        self.x = 0.0
        self.drift = drift
        self.noise = noise

    def next(self) -> float:
        self.x = 0.98*self.x + self.drift + random.gauss(0, self.noise)
        return float(self.x)


# =========================
# Core Entropy Accountant
# =========================

@dataclasses.dataclass
class ArrowPoint:
    Htilde: float
    Y: float
    Z: float

class EntropyAccountant:
    """
    Maintains a rolling window of numeric samples.
    Computes normalized entropy H~ in [0,1] using a fixed bin count,
    then slope Y and curvature Z using central differences scaled by T*.
    """
    def __init__(self, dt: float, bins: int, window: int, Tstar: float):
        self.dt = float(dt)
        self.bins = int(bins)
        self.window = int(window)
        self.Tstar = float(Tstar)

        self.buf: Deque[float] = collections.deque(maxlen=self.window)
        self.H_hist: Deque[float] = collections.deque(maxlen=max(3, self.window))
        self._edges: Optional[np.ndarray] = None

    def _update_edges(self, values: np.ndarray):
        vmin, vmax = float(values.min()), float(values.max())
        if vmin == vmax:
            vmin, vmax = vmin - 0.5, vmax + 0.5
        span = vmax - vmin
        pad = 0.05 * span
        self._edges = np.linspace(vmin - pad, vmax + pad, self.bins + 1)

    def _entropy_normalized(self, values: np.ndarray) -> float:
        if self._edges is None:
            self._update_edges(values)
        vmin, vmax = float(values.min()), float(values.max())
        e0, e1 = self._edges[0], self._edges[-1]
        if vmin < e0 or vmax > e1:
            self._update_edges(values)

        hist, _ = np.histogram(values, bins=self._edges, density=False)
        total = int(hist.sum())
        if total == 0:
            return 0.0
        p = hist.astype(np.float64) / total
        p = p[p > 0]
        H = -np.sum(p * (np.log(p) / np.log(2.0)))  # log base 2
        Hmax = math.log(self.bins, 2) if self.bins > 1 else 1.0
        Htilde = float(H / Hmax) if Hmax > 0 else 0.0
        return max(0.0, min(1.0, Htilde))

    def _derivatives(self) -> tuple[float, float]:
        if len(self.H_hist) < 3:
            return 0.0, 0.0
        Hm2, Hm1, H0 = self.H_hist[-3], self.H_hist[-2], self.H_hist[-1]
        dHdt = (H0 - Hm2) / (2.0 * self.dt)
        d2Hdt2 = (H0 - 2.0*Hm1 + Hm2) / (self.dt * self.dt)
        Y = dHdt * self.Tstar
        Z = d2Hdt2 * (self.Tstar * self.Tstar)
        return float(Y), float(Z)

    def step(self, x: float) -> ArrowPoint:
        self.buf.append(float(x))
        vals = np.fromiter(self.buf, dtype=np.float64)
        Ht = self._entropy_normalized(vals)
        self.H_hist.append(Ht)
        Y, Z = self._derivatives()
        return ArrowPoint(Htilde=Ht, Y=Y, Z=Z)


# =========================
# EeFrame emitter
# =========================

def ee_frame(ap: ArrowPoint,
             agent_id: int = 101,
             mode_bias_scale: float = 1.0,
             ttl_ms: int = 2000,
             confidence: float = 0.5) -> dict:
    """
    Build a minimal EeFrame-like JSON for logging.
    """
    mode_bias = 0.5 + 0.5 * math.tanh(ap.Y * 0.25 * mode_bias_scale)
    intensity = min(1.0, 0.5 * (abs(ap.Y) + 0.10 * abs(ap.Z)))
    return {
        "event": "ee.nudge",
        "schema_version": "ee-0.3",
        "frame_id": os.urandom(8).hex(),
        "agent_id": agent_id,
        "issued_at_ms": int(time.time() * 1000),
        "ttl_ms": ttl_ms,
        "confidence": float(confidence),
        "mode_bias": float(mode_bias),
        "intensity": float(intensity),
        "constraints": {"caps_wip": 3, "queue_policy": "OldestFirst", "emergency": False},
        "Htilde": round(ap.Htilde, 3),
        "Y": round(ap.Y, 3),
        "Z": round(ap.Z, 3),
    }


# =========================
# UI (Dash 3D) with visual scaling
# =========================

class Display3D:
    def __init__(self, host="127.0.0.1", port=8050, dt: float = 0.25,
                 viz_y_gain: float = 1.0, viz_z_gain: float = 2.0,
                 viz_aspect: str = "1,1,1"):
        self.host = host
        self.port = port
        self.dt = dt
        self.viz_y_gain = float(viz_y_gain)
        self.viz_z_gain = float(viz_z_gain)

        try:
            ax = [float(s) for s in viz_aspect.split(",")]
            self.aspect = dict(x=ax[0], y=ax[1], z=ax[2]) if len(ax) == 3 else dict(x=1, y=1, z=1)
        except Exception:
            self.aspect = dict(x=1, y=1, z=1)

        self.app = Dash(__name__)
        self._build_layout()

        self.history_len = 400
        self.H_hist: Deque[float] = collections.deque(maxlen=self.history_len)
        self.Y_hist: Deque[float] = collections.deque(maxlen=self.history_len)
        self.Z_hist: Deque[float] = collections.deque(maxlen=self.history_len)
        self.last_frame = {}

    def _build_layout(self):
        self.app.layout = html.Div([
            html.H2("Entropy Engine MVP — 3D Arrow (H~, Y, Z)"),
            html.Div([
                dcc.Graph(id="arrow3d", style={"height": "520px"}),
                dcc.Interval(id="tick", interval=500, n_intervals=0),
            ]),
            html.Pre(id="eeframe", style={"background": "#111", "color": "#0f0", "padding": "8px",
                                          "whiteSpace": "pre-wrap", "fontSize": "12px"}),
        ], style={"fontFamily": "Segoe UI, sans-serif", "margin": "10px"})

        @self.app.callback(
            Output("arrow3d", "figure"),
            Output("eeframe", "children"),
            Input("tick", "n_intervals"),
            prevent_initial_call=False,
        )
        def _update(_n):
            if not (self.H_hist and self.Y_hist and self.Z_hist):
                fig = go.Figure()
                fig.update_layout(scene=dict(
                    xaxis_title="H~",
                    yaxis_title=f"Y (×{self.viz_y_gain:g})",
                    zaxis_title=f"Z (×{self.viz_z_gain:g})",
                ), margin=dict(l=0, r=0, t=20, b=0))
                return fig, "awaiting data…"

            # true values
            x, y, z = self.H_hist[-1], self.Y_hist[-1], self.Z_hist[-1]
            yg, zg = self.viz_y_gain, self.viz_z_gain

            # plot-only scaled values
            x_plot, y_plot, z_plot = x, y*yg, z*zg

            fig = go.Figure()
            # arrow
            fig.add_trace(go.Scatter3d(
                x=[0, x_plot], y=[0, y_plot], z=[0, z_plot],
                mode="lines+markers",
                line=dict(width=6),
                marker=dict(size=4)
            ))
            # trail (scaled)
            if len(self.H_hist) > 2:
                fig.add_trace(go.Scatter3d(
                    x=list(self.H_hist),
                    y=[v*yg for v in self.Y_hist],
                    z=[v*zg for v in self.Z_hist],
                    mode="lines",
                    line=dict(width=2),
                    name="trail"
                ))

            # axis ranges from scaled histories
            yr = max(1.0, 1.2 * max(1e-6, max(abs(v*yg) for v in self.Y_hist)))
            zr = max(1.0, 1.2 * max(1e-6, max(abs(v*zg) for v in self.Z_hist)))

            fig.update_layout(scene=dict(
                xaxis_title="H~",
                yaxis_title=f"Y (×{yg:g})",
                zaxis_title=f"Z (×{zg:g})",
                xaxis=dict(range=[0, 1]),
                yaxis=dict(range=[-yr, yr]),
                zaxis=dict(range=[-zr, zr]),
                aspectmode="manual",
                aspectratio=self.aspect,
            ), margin=dict(l=0, r=0, t=20, b=0))

            txt = json.dumps(self.last_frame, indent=2)
            return fig, txt

    def push(self, ap: ArrowPoint, frame: dict):
        self.H_hist.append(ap.Htilde)
        self.Y_hist.append(ap.Y)
        self.Z_hist.append(ap.Z)
        self.last_frame = frame

    def run(self):
        self.app.run(debug=False, host=self.host, port=self.port)


# =========================
# Main loop
# =========================

def main():
    args = build_arg_parser().parse_args()

    # ----- pick source -----
    if args.source == "csv":
        src = CsvSource(path=args.path, loop=args.loop)
    elif args.source == "tcp":
        src = TcpSource(host=args.tcp_host, port=args.tcp_port, default=0.0)
    elif args.source == "module":
        src = ModuleSource(datatype=args.datatype, uf=args.uf, seed=args.seed, dt=args.dt)
    else:
        src = RandomWalkSource()

    # ----- construct engine & UI -----
    eng = EntropyAccountant(dt=args.dt, bins=args.bins, window=args.window, Tstar=args.Tstar)
    ui = Display3D(host=args.host, port=args.port, dt=args.dt,
                   viz_y_gain=args.viz_y_gain, viz_z_gain=args.viz_z_gain,
                   viz_aspect=args.viz_aspect)

    print(f">> Entropy Engine MVP starting: source={args.source} dt={args.dt}s bins={args.bins} window={args.window}",
          file=sys.stderr)

    # warm-up so histogram stabilizes a bit for nicer UI scaling
    warmup_ticks = max(10, int(2.0 / max(1e-6, args.dt)))  # ~2 seconds worth
    next_tick = time.perf_counter()

    try:
        # run loop; start Dash in a background thread after warm-up
        while True:
            now = time.perf_counter()
            if now < next_tick:
                time.sleep(min(0.001, next_tick - now))
                continue
            next_tick += args.dt

            # 1) sample
            x = src.next()

            # 2) step engine
            ap = eng.step(x)

            # 3) simple confidence heuristic from short-term H~ volatility
            if len(eng.H_hist) > 2:
                nwin = max(5, int(1.0/args.dt))
                H_vol = float(np.std(list(eng.H_hist)[-nwin:]))
            else:
                H_vol = 0.5
            conf = max(0.5, min(1.0, 1.0 - 2.0 * H_vol))

            # 4) build & print EeFrame
            frame = ee_frame(ap, confidence=conf)
            print(json.dumps(frame), flush=True)

            # 5) push to UI buffers
            ui.push(ap, frame)

            # Start server after warmup; keep loop non-blocking
            if warmup_ticks > 0:
                warmup_ticks -= 1
                if warmup_ticks == 0:
                    import threading
                    threading.Thread(target=ui.run, daemon=True).start()

    except KeyboardInterrupt:
        print("\n>> Halted by user", file=sys.stderr)


if __name__ == "__main__":
    main()
