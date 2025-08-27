#!/usr/bin/env python3
# ee_mvp.py — Entropy Engine MVP with Cone-based 3D Arrow rendering
# ---------------------------------------------------------------
# - Sources: CSV or TCP (line-delimited values). Optional demo generator runs separately.
# - Computes H~ (entropy), slope (Y), curvature (Z).
# - Renders a 3D Arrow using Plotly Cone (robust across browsers).
# - Includes visual-only scaling flags for better depth and visibility.
#
# Quick start (TCP example; start your generator on 127.0.0.1:9009 first):
#   python ee_mvp.py --source tcp --tcp_host 127.0.0.1 --tcp_port 9009 --dt 0.25 --bins 24 --window 180 \
#                    --viz_tail --viz_y_gain 2 --viz_z_gain 4 --viz_aspect 1,1.2,1.8
#
# CSV example:
#   python ee_mvp.py --source csv --path telemetry.csv --dt 0.25 --bins 24 --window 180

import argparse
import json
import math
import socket
import threading
import time
import uuid
from collections import deque
from datetime import datetime

import numpy as np
import pandas as pd
import plotly.graph_objects as go

from dash import Dash, dcc, html
from dash.dependencies import Input, Output, State


# -----------------------------
# Utilities: parsing & coercion
# -----------------------------

def coerce_value(token: str):
    """
    Convert an incoming token (from CSV/TCP) into a scalar for entropy.
    - Prefer float if parseable.
    - If pure char/word: map characters to numeric via simple ordinal sum normalized.
    - If empty/invalid, return None.
    """
    if token is None:
        return None
    t = str(token).strip()
    if t == "":
        return None
    # Try numeric
    try:
        return float(t)
    except Exception:
        pass
    # Map string to numeric in a stable way (entropy-friendly)
    # Sum of (normalized ords), then scale.
    s = 0.0
    for ch in t:
        s += (ord(ch) % 128) / 127.0
    return s / max(1, len(t))


# -------------------------
# Data sources: CSV and TCP
# -------------------------

class CSVSource:
    def __init__(self, path: str):
        self.path = path
        # Accept generic CSV with either a header 'value' or single column
        try:
            df = pd.read_csv(path)
            if "value" in df.columns:
                self.values = df["value"].tolist()
            else:
                # take first column
                self.values = df.iloc[:, 0].tolist()
        except Exception as e:
            raise RuntimeError(f"Failed to read CSV '{path}': {e}")
        self.idx = 0

    def next(self):
        if not self.values:
            return None
        v = self.values[self.idx % len(self.values)]
        self.idx += 1
        return coerce_value(v)


class TCPSource:
    """
    Connect to a TCP server (e.g., test_stream_gen.py) that emits one value per line.
    Maintain a small queue; the UI tick consumes most-recent.
    """
    def __init__(self, host: str, port: int, timeout: float = 5.0, bufsize: int = 4096):
        self.host = host
        self.port = port
        self.timeout = timeout
        self.bufsize = bufsize
        self._sock = None
        self._buf = b""
        self._q = deque(maxlen=1024)
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._reader, daemon=True)
        self._thread.start()

    def _reader(self):
        while not self._stop.is_set():
            try:
                if self._sock is None:
                    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                    s.settimeout(self.timeout)
                    s.connect((self.host, self.port))
                    s.settimeout(None)
                    self._sock = s
                chunk = self._sock.recv(self.bufsize)
                if not chunk:
                    # server closed
                    self._sock.close()
                    self._sock = None
                    time.sleep(0.25)
                    continue
                self._buf += chunk
                while b"\n" in self._buf:
                    line, self._buf = self._buf.split(b"\n", 1)
                    token = line.decode("utf-8", errors="ignore").strip()
                    if token != "":
                        self._q.append(token)
            except Exception:
                # reconnect loop
                try:
                    if self._sock:
                        self._sock.close()
                except Exception:
                    pass
                self._sock = None
                time.sleep(0.5)

    def next(self):
        if self._q:
            token = self._q.pop()  # most recent
            return coerce_value(token)
        return None

    def close(self):
        self._stop.set()
        try:
            if self._sock:
                self._sock.close()
        except Exception:
            pass


# -------------------------
# Entropy Accountant (MVP)
# -------------------------

class EntropyAccountant:
    """
    Sliding window entropy with simple histogram binning.
    - Window length expressed in seconds; we convert to samples via dt.
    - H = -sum p log2 p ; H~ normalized by log2(k) where k = number of nonzero bins.
    - Slope Y via first difference of smoothed H~.
    - Curvature Z via second difference.
    """
    def __init__(self, bins: int, dt: float, window_seconds: float,
                 alpha: float = 0.2, tstar: float = 0.0):
        self.bins = max(2, int(bins))
        self.dt = float(dt)
        self.window_seconds = float(window_seconds)
        self.window_n = max(2, int(round(self.window_seconds / max(1e-6, self.dt))))
        self.alpha = float(alpha)  # EMA for H~ smoothing
        self.tstar = float(tstar)  # Reserved for thresholding/experiments

        self.window = deque(maxlen=self.window_n)
        self.last_Ht = None  # smoothed H~
        self.prev_Ht = None
        self.prev2_Ht = None

    def update(self, x: float):
        if x is not None and np.isfinite(x):
            self.window.append(float(x))

        Htilde_raw = 0.0
        if len(self.window) >= 2:
            arr = np.asarray(self.window, dtype=float)
            # Dynamic bin edges: robust to outliers
            vmin, vmax = np.nanmin(arr), np.nanmax(arr)
            if not np.isfinite(vmin) or not np.isfinite(vmax) or vmin == vmax:
                vmin, vmax = float(min(0.0, vmin)), float(max(1.0, vmax + 1e-9))
            counts, _edges = np.histogram(arr, bins=self.bins, range=(vmin, vmax))
            total = counts.sum()
            if total > 0:
                p = counts[counts > 0].astype(float) / total
                H = -(p * np.log2(p)).sum()
                k = len(p)
                Hnorm = math.log2(k) if k > 0 else 1.0
                Htilde_raw = H / Hnorm if Hnorm > 0 else 0.0
                Htilde_raw = float(np.clip(Htilde_raw, 0.0, 1.0))
            else:
                Htilde_raw = 0.0
        # Smooth H~ with EMA
        if self.last_Ht is None:
            Ht = Htilde_raw
        else:
            Ht = self.alpha * Htilde_raw + (1 - self.alpha) * self.last_Ht

        # Derivatives (finite differences on smoothed series)
        Y = 0.0
        Z = 0.0
        if self.last_Ht is not None:
            Y = (Ht - self.last_Ht) / self.dt
        if self.prev_Ht is not None and self.last_Ht is not None:
            Z = (Ht - 2 * self.last_Ht + self.prev_Ht) / (self.dt ** 2)

        # shift history
        self.prev2_Ht = self.prev_Ht
        self.prev_Ht = self.last_Ht
        self.last_Ht = Ht

        return float(Ht), float(Y), float(Z)


# -------------------
# Dash / Plotly 3D UI
# -------------------

class ArrowUI:
    def __init__(self, args, source):
        self.args = args
        self.source = source

        # History of tips for trailing polyline (visual only)
        self.trail_len = int(args.trail_len)
        self.trail = deque(maxlen=self.trail_len)

        self.ent = EntropyAccountant(
            bins=args.bins,
            dt=args.dt,
            window_seconds=args.window,
            alpha=args.alpha,
            tstar=args.Tstar
        )

        self.app = Dash(__name__)
        self.app.layout = html.Div([
            html.H3("Entropy Engine MVP — 3D Arrow (Cone)"),
            dcc.Graph(id="arrow-3d", style={"height": "70vh"}),
            html.Pre(id="status", style={"whiteSpace": "pre-wrap", "fontSize": "14px"}),
            dcc.Interval(id="tick", interval=int(args.dt * 1000), n_intervals=0)
        ])

        # Set up callbacks
        self.app.callback(
            Output("arrow-3d", "figure"),
            Output("status", "children"),
            Input("tick", "n_intervals"),
            State("status", "children")
        )(self._on_tick)

    def _make_figure(self, x, y, z):
        args = self.args

        # Apply visual-only gains
        yv = y * args.viz_y_gain
        zv = z * args.viz_z_gain

        # Optional global gain
        xg = x * args.viz_arrow_gain
        yg = yv * args.viz_arrow_gain
        zg = zv * args.viz_arrow_gain

        # Ensure non-zero vector for cone rendering
        mag = math.sqrt(xg * xg + yg * yg + zg * zg)
        if mag < 1e-12:
            zg = 1e-3
            mag = 1e-3

        fig = go.Figure()

        # Cone arrow anchored at the origin (tail)
        if args.viz_arrow_mode == "cone":
            fig.add_trace(go.Cone(
                x=[0.0], y=[0.0], z=[0.0],
                u=[xg], v=[yg], w=[zg],
                anchor="tail",
                sizemode=args.viz_cone_sizemode,  # "absolute" or "scaled"
                sizeref=args.viz_cone_sizeref,
                showscale=False,
                colorscale=[[0, "royalblue"], [1, "royalblue"]],
                opacity=0.95
            ))
        else:
            # fallback line mode (no head)
            fig.add_trace(go.Scatter3d(
                x=[0.0, xg], y=[0.0, yg], z=[0.0, zg],
                mode="lines",
                line=dict(width=6, color="royalblue"),
                name="arrow"
            ))

        # Optional tail (thin line origin -> tip) to aid orientation
        if args.viz_tail:
            fig.add_trace(go.Scatter3d(
                x=[0.0, xg], y=[0.0, yg], z=[0.0, zg],
                mode="lines",
                line=dict(width=2, color="rgba(30,30,30,0.35)"),
                showlegend=False
            ))

        # Trail of previous tips (polyline)
        if len(self.trail) >= 2:
            xt, yt, zt = zip(*self.trail)
            fig.add_trace(go.Scatter3d(
                x=xt, y=yt, z=zt,
                mode="lines",
                line=dict(width=3, color="rgba(50,50,50,0.35)"),
                name="trail",
                showlegend=False
            ))

        # Scene & axes
        scene = dict(
            xaxis=dict(title="H~ (0..1)", range=[0, 1], backgroundcolor="rgb(250,250,250)"),
            yaxis=dict(title="Y (slope)", backgroundcolor="rgb(250,250,250)"),
            zaxis=dict(title="Z (curvature)", backgroundcolor="rgb(250,250,250)"),
        )

        # Aspect ratio control
        if args.viz_aspect and args.viz_aspect.lower() not in ("auto", "none"):
            try:
                ax = [float(t) for t in args.viz_aspect.split(",")]
                if len(ax) == 3 and all(a > 0 for a in ax):
                    scene.update(aspectmode="manual", aspectratio=dict(x=ax[0], y=ax[1], z=ax[2]))
                else:
                    scene.update(aspectmode="auto")
            except Exception:
                scene.update(aspectmode="auto")
        else:
            scene.update(aspectmode="auto")

        fig.update_layout(
            scene=scene,
            margin=dict(l=10, r=10, t=40, b=10),
            title="Entropy Arrow (Cone) — position=X(H~), direction=(Y,Z)",
            paper_bgcolor="white",
            plot_bgcolor="white"
        )
        return fig

    def _on_tick(self, n, prev_status):
        # 1) Pull next sample
        val = self.source.next()
        Ht, Y, Z = self.ent.update(val)

        # 2) Update trail with current tip (visual coordinates after scaling)
        xv = Ht
        yv = Y * self.args.viz_y_gain * self.args.viz_arrow_gain
        zv = Z * self.args.viz_z_gain * self.args.viz_arrow_gain
        self.trail.append((xv, yv, zv))

        # 3) Build figure
        fig = self._make_figure(Ht, Y, Z)

        # 4) Emit a minimal EeFrame to console (nudge style)
        frame = {
            "event": "ee.nudge",
            "schema_version": "ee-0.3",
            "frame_id": str(uuid.uuid4()),
            "agent_id": int(self.args.agent_id),
            "issued_at_ms": int(time.time() * 1000),
            "ttl_ms": 2000,
            "confidence": float(self.args.confidence),
            "mode_bias": float(self.args.mode_bias),
            "intensity": float(self.args.intensity),
            "constraints": {
                "caps_wip": int(self.args.caps_wip),
                "queue_policy": "OldestFirst",
                "emergency": False
            },
            "Htilde": round(Ht, 3),
            "Y": round(Y, 3),
            "Z": round(Z, 3)
        }
        print(json.dumps(frame), flush=True)

        # 5) Build status text
        status = (
            f"[{datetime.now().strftime('%H:%M:%S')}] "
            f"val={val!r}  H~={Ht:.3f}  Y={Y:.3f}  Z={Z:.3f}  "
            f"(trail={len(self.trail)}/{self.trail_len})"
        )
        return fig, status

    def run(self):
        # Dash 2+: use app.run(...) not run_server(...)
        # Try port, then fall back to next if busy (optional convenience)
        host = self.args.ui_host
        port = int(self.args.ui_port)
        max_tries = 5
        for i in range(max_tries):
            try:
                self.app.run(debug=False, host=host, port=port)
                break
            except OSError as e:
                if "Address already in use" in str(e) and i < (max_tries - 1):
                    port += 1
                    print(f"[ui] port in use, trying {port} …")
                    continue
                raise


# --------------
# CLI & bootstrap
# --------------

def build_arg_parser():
    p = argparse.ArgumentParser(
        description="Entropy Engine MVP — real-time entropy arrow with Cone-based 3D rendering."
    )
    # Data sources
    p.add_argument("--source", choices=["csv", "tcp"], default="csv",
                   help="Data source type: csv file or tcp stream.")
    p.add_argument("--path", type=str, default="telemetry.csv",
                   help="CSV path when --source csv")
    p.add_argument("--tcp_host", type=str, default="127.0.0.1",
                   help="TCP host when --source tcp")
    p.add_argument("--tcp_port", type=int, default=9009,
                   help="TCP port when --source tcp")

    # Engine params
    p.add_argument("--dt", type=float, default=0.25,
                   help="Tick interval (seconds). Also CSV replay step.")
    p.add_argument("--bins", type=int, default=24,
                   help="Histogram bin count for entropy.")
    p.add_argument("--window", type=float, default=180.0,
                   help="Entropy window length in seconds.")
    p.add_argument("--alpha", type=float, default=0.2,
                   help="EMA smoothing factor for H~ (0..1).")
    p.add_argument("--Tstar", type=float, default=0.0,
                   help="Reserved param for thresholding/experiments.")

    # UI / Viz params
    p.add_argument("--ui_host", type=str, default="127.0.0.1",
                   help="Dash host.")
    p.add_argument("--ui_port", type=int, default=8050,
                   help="Dash port.")
    p.add_argument("--trail_len", type=int, default=240,
                   help="How many tips to keep in the trail.")
    p.add_argument("--viz_y_gain", type=float, default=1.0,
                   help="Visual gain for Y (slope).")
    p.add_argument("--viz_z_gain", type=float, default=1.0,
                   help="Visual gain for Z (curvature).")
    p.add_argument("--viz_aspect", type=str, default="auto",
                   help="Aspect ratio 'x,y,z' or 'auto'. Example: 1,1,1.6")
    p.add_argument("--viz_tail", action="store_true",
                   help="Draw a faint tail origin->tip.")
    p.add_argument("--viz_arrow_mode", choices=["cone", "line"], default="cone",
                   help="Vector drawing mode; 'cone' recommended.")
    p.add_argument("--viz_arrow_gain", type=float, default=1.0,
                   help="Visual gain for overall arrow length.")
    p.add_argument("--viz_cone_sizeref", type=float, default=0.6,
                   help="Cone head size reference (absolute mode).")
    p.add_argument("--viz_cone_sizemode", choices=["absolute", "scaled"], default="absolute",
                   help="Cone sizemode; 'absolute' for predictable size.")

    # EeFrame / nudge cosmetics
    p.add_argument("--agent_id", type=int, default=101)
    p.add_argument("--confidence", type=float, default=0.999)
    p.add_argument("--mode_bias", type=float, default=0.02)
    p.add_argument("--intensity", type=float, default=1.0)
    p.add_argument("--caps_wip", type=int, default=3)

    return p


def build_source(args):
    if args.source == "csv":
        return CSVSource(args.path)
    elif args.source == "tcp":
        return TCPSource(args.tcp_host, args.tcp_port)
    else:
        raise ValueError(f"Unsupported source: {args.source!r}")


def main():
    args = build_arg_parser().parse_args()
    src = build_source(args)
    ui = ArrowUI(args, src)
    try:
        ui.run()
    finally:
        # Clean up source if needed
        if isinstance(src, TCPSource):
            src.close()


if __name__ == "__main__":
    main()
