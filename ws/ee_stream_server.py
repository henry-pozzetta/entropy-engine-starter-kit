## `ws/ee_stream_server.py`
"""
Local WebSocket stream for EE metrics (H~, Y, Z) at ~20 Hz.
- Offline-only by default: binds 127.0.0.1
- Ring buffer so new viewers see immediate context
- Profile switching via inbound WS JSON {"cmd":"set_profile","value":"calm|busy|jammy"}

Run:
  py -3 -m pip install websockets numpy
  py ws\ee_stream_server.py
"""
from __future__ import annotations
import asyncio
import json
import math
import random
import time
import collections
from typing import Dict, Set

import websockets
from websockets.server import WebSocketServerProtocol

from ee.stream import stream_entropy

HOST, PORT = "127.0.0.1", 8765
CLIENTS: Set[WebSocketServerProtocol] = set()
RING = collections.deque(maxlen=200)  # last ~10s at 20 Hz
profile = "calm"


async def broadcast(msg: Dict):
    data = json.dumps(msg, separators=(",", ":"))
    RING.append(data)
    if CLIENTS:
        # best-effort fanout; skip slow clients by not awaiting individually
        await asyncio.gather(*(ws.send(data) for ws in list(CLIENTS)), return_exceptions=True)


async def handler(ws: WebSocketServerProtocol):
    global profile
    CLIENTS.add(ws)
    try:
        # Warm-up replay so the path isn't empty
        for d in list(RING):
            await ws.send(d)
        async for raw in ws:
            try:
                m = json.loads(raw)
                if m.get("cmd") == "set_profile":
                    val = str(m.get("value", "calm")).lower()
                    if val in {"calm", "busy", "jammy"}:
                        profile = val
            except Exception:
                # Ignore malformed messages
                pass
    finally:
        CLIENTS.discard(ws)


def sample_gen():
    """Deterministic demo source in [0,1] with behavior controlled by `profile`."""
    H = 0.5
    yph = 0.0
    zph = 0.0
    while True:
        kind = profile  # read each loop for dynamic switching
        if kind == "jammy" and random.random() < 0.04:
            H = min(1.0, H + 0.12)
        if kind == "busy" and random.random() < 0.02:
            H = max(0.0, H - 0.08)
        y = 0.10 * math.sin(yph)
        z = 0.16 * math.sin(zph * 0.7)
        yph += 0.12
        zph += 0.18
        H = max(0.0, min(1.0, H + 0.03 * y + 0.5 * z * 0.05))
        yield H


async def loop():
    dt = 0.05  # 20 Hz-ish
    ent_stream = stream_entropy(sample_gen(), bins=32, window=256, dt=dt, ema=0.2)
    while True:
        msg = next(ent_stream)
        msg["t"] = time.time()
        msg["profile"] = profile
        await broadcast(msg)
        await asyncio.sleep(dt)


async def main():
    print(f"EE WS: ws://{HOST}:{PORT}/  (profiles: calm|busy|jammy)")
    async with websockets.serve(
        handler,
        HOST,
        PORT,
        ping_interval=20,
        ping_timeout=20,
        # origins=["http://localhost", "http://127.0.0.1"],  # tighten if embedding
    ):
        await loop()


if __name__ == "__main__":
    asyncio.run(main())