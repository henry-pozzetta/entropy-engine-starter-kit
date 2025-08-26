# test_stream_gen.py
# EE Test Data Stream Generator: standalone TCP server or in-process plugin
from __future__ import annotations
import argparse, math, random, socket, string, sys, time, json
from dataclasses import dataclass
from typing import Iterator, Union, List, Optional

# ---------- config & helpers ----------

@dataclass
class StreamConfig:
    datatype: str       # '123' | 'abc' | 'sym' | 'mix'
    clock: float        # seconds per tick (emission rate)
    runtime: float      # total seconds to run (TCP/stdout modes)
    uf: float           # Unexpected Factor in [0,1]
    seed: int = 42      # RNG seed for reproducibility
    # transport
    mode: str = "tcp"   # 'tcp' | 'stdout' | 'module'
    host: str = "127.0.0.1"
    port: int = 9009
    fmt: str = "plain"  # 'plain' | 'json'
    # module mode extra
    dt_for_module: float = 1.0  # logical dt used when polled in module mode

def _norm_datatype(dt: str) -> str:
    # Accept '--123' or '123', etc.
    dt = dt.strip()
    if dt.startswith("--"):
        dt = dt[2:]
    dt = dt.lower()
    if dt not in ("123", "abc", "sym", "mix"):
        raise ValueError("datatype must be one of: 123, abc, sym, mix (or with leading --)")
    return dt

# ---------- generator core ----------

class Generator:
    """Deterministic baseline + stochastic perturbations governed by uf."""
    def __init__(self, cfg: StreamConfig):
        self.cfg = cfg
        random.seed(cfg.seed)
        self.t0 = time.perf_counter()
        self._k = 0  # index for cyclic symbol baselines
        self._last_emit_t = self.t0

        self.alphabets = {
            "123": [str(d) for d in range(10)],
            "abc": list(string.ascii_lowercase),
            "sym": list("!@#$%^&*?-+=:;")
        }
        # regime state
        self.regime_bias = 0.0
        self.next_regime = self.t0 + self._regime_interval()

        # counters for observability
        self.count = 0
        self.c_spikes = 0
        self.c_switch = 0
        self.c_drop = 0
        self.c_dup = 0

        # validate
        if self.cfg.clock <= 0:  raise ValueError("clock must be > 0")
        if self.cfg.runtime < 0: raise ValueError("runtime must be >= 0")
        if not (0.0 <= self.cfg.uf <= 1.0): raise ValueError("uf must be in [0,1]")

    # ---- baseline patterns ----
    def _baseline_numeric(self, t: float) -> float:
        # quasi-periodic components + slow drift => long non-trivial pattern
        return (math.sin(2.0*t) +
                0.7*math.sin(math.pi*math.sqrt(2)*t) +
                0.05*math.sin(0.1*t) +
                0.001*t)

    def _baseline_symbol(self, alphabet: List[str]) -> str:
        s = alphabet[self._k % len(alphabet)]
        self._k += 1
        return s

    # ---- perturbations derived from uf ----
    def _noise(self) -> float:
        # std grows with uf
        return random.gauss(0.0, 0.25*self.cfg.uf)

    def _spike(self) -> float:
        # probability ∝ uf^2, magnitude ∝ uf
        p = (self.cfg.uf**2) * 0.05
        if random.random() < p:
            self.c_spikes += 1
            return random.choice([-1,1]) * (2.0 + 8.0*self.cfg.uf)
        return 0.0

    def _regime_interval(self) -> float:
        base = 30.0
        scale = max(0.1, 1.0 - self.cfg.uf)  # higher uf => shorter intervals
        return max(5.0, base*scale)

    def _maybe_regime_switch(self, now: float):
        if now >= self.next_regime:
            self.regime_bias += random.uniform(-1.0, 1.0) * (0.5 + self.cfg.uf)
            self.next_regime = now + self._regime_interval()
            self.c_switch += 1

    # ---- dropout/duplicate control ----
    def _maybe_dropout(self) -> bool:
        # small chance to skip emission
        p = 0.01 * self.cfg.uf
        if random.random() < p:
            self.c_drop += 1
            return True
        return False

    def _maybe_duplicate(self) -> bool:
        p = 0.01 * self.cfg.uf
        if random.random() < p:
            self.c_dup += 1
            return True
        return False

    # ---- timing jitter (stays around target clock) ----
    def _sleep_to_next_tick(self, now: float):
        clk = self.cfg.clock
        # nominal next boundary:
        nominal = self._last_emit_t + clk
        # jitter up to ±(uf * 15%) of clk
        jitter = (random.random()*2 - 1) * (self.cfg.uf * 0.15 * clk)
        target = max(nominal + jitter, now)  # never sleep into the past
        delay = max(0.0, target - time.perf_counter())
        time.sleep(delay)
        self._last_emit_t = time.perf_counter()

    # ---- main stream (for TCP/stdout modes) ----
    def stream(self) -> Iterator[Union[float, str]]:
        while True:
            now = time.perf_counter()
            if self.cfg.runtime and (now - self.t0) >= self.cfg.runtime:
                return
            self._maybe_regime_switch(now)

            # produce a value
            if self.cfg.datatype in ("123", "mix"):
                val_num = (self._baseline_numeric(now - self.t0) +
                           self.regime_bias + self._noise() + self._spike())
                if self.cfg.datatype == "mix" and random.random() < 0.25:
                    alph_mix = self.alphabets["abc"] + self.alphabets["sym"]
                    val = self._baseline_symbol(alph_mix)
                else:
                    val = val_num
            elif self.cfg.datatype == "abc":
                val = self._baseline_symbol(self.alphabets["abc"])
            else:  # "sym"
                val = self._baseline_symbol(self.alphabets["sym"])

            # dropout/duplicate handling
            if not self._maybe_dropout():
                yield val
                self.count += 1
                if self._maybe_duplicate():
                    yield val
                    self.count += 1

            # wait for next tick (with jitter)
            self._sleep_to_next_tick(now)

    # ---- module polling mode (no sleeping; step by step) ----
    def next_for_module(self, step: int) -> Union[float, str]:
        # time advances by cfg.dt_for_module per step (consumer's tick)
        t = step * self.cfg.dt_for_module
        self._maybe_regime_switch(self.t0 + t)

        if self.cfg.datatype in ("123", "mix"):
            val_num = self._baseline_numeric(t) + self.regime_bias + self._noise() + self._spike()
            if self.cfg.datatype == "mix" and random.random() < 0.25:
                alph_mix = self.alphabets["abc"] + self.alphabets["sym"]
                return self._baseline_symbol(alph_mix)
            return val_num
        elif self.cfg.datatype == "abc":
            return self._baseline_symbol(self.alphabets["abc"])
        else:
            return self._baseline_symbol(self.alphabets["sym"])

# ---------- transports ----------

def run_stdout(cfg: StreamConfig):
    g = Generator(cfg)
    for v in g.stream():
        if cfg.fmt == "json":
            print(json.dumps({"value": v}), flush=True)
        else:
            print(v, flush=True)
    _summary(g)

def run_tcp(cfg: StreamConfig):
    g = Generator(cfg)
    srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    srv.bind((cfg.host, cfg.port))
    srv.listen(1)
    print(f"[gen] listening on {cfg.host}:{cfg.port}")
    conn: Optional[socket.socket] = None
    try:
        conn, addr = srv.accept()
        print(f"[gen] client connected: {addr}")
        for v in g.stream():
            line = json.dumps({"value": v}) + "\n" if cfg.fmt == "json" else f"{v}\n"
            try:
                conn.sendall(line.encode("utf-8"))
            except (BrokenPipeError, ConnectionResetError):
                print("[gen] client disconnected; stopping.")
                break
    finally:
        if conn: conn.close()
        srv.close()
        _summary(g)

def _summary(g: Generator):
    print(json.dumps({
        "samples_emitted": g.count,
        "spikes": g.c_spikes,
        "regime_switches": g.c_switch,
        "dropouts": g.c_drop,
        "duplicates": g.c_dup
    }, indent=2), file=sys.stderr)

# ---------- CLI ----------

def parse_args() -> StreamConfig:
    p = argparse.ArgumentParser(description="EE Test Data Stream Generator")
    p.add_argument("--datatype", type=str, default="123", help="123|abc|sym|mix (or --123 style)")
    p.add_argument("--clock", type=float, default=1.0, help="seconds per tick (emission rate)")
    p.add_argument("--runtime", type=float, default=60.0, help="run time in seconds (0 = forever)")
    p.add_argument("--uf", type=float, default=0.2, help="Unexpected Factor [0..1]")
    p.add_argument("--seed", type=int, default=42, help="RNG seed")
    p.add_argument("--mode", type=str, default="tcp", choices=["tcp","stdout","module"])
    p.add_argument("--host", type=str, default="127.0.0.1")
    p.add_argument("--port", type=int, default=9009)
    p.add_argument("--fmt", type=str, default="plain", choices=["plain","json"])
    p.add_argument("--dt_for_module", type=float, default=1.0)
    a = p.parse_args()
    return StreamConfig(
        datatype=_norm_datatype(a.datatype),
        clock=a.clock, runtime=a.runtime, uf=a.uf, seed=a.seed,
        mode=a.mode, host=a.host, port=a.port, fmt=a.fmt,
        dt_for_module=a.dt_for_module
    )

if __name__ == "__main__":
    try:
        cfg = parse_args()
    except Exception as e:
        print(f"invalid arguments: {e}", file=sys.stderr)
        sys.exit(2)

    if cfg.mode == "stdout":
        run_stdout(cfg)
    elif cfg.mode == "tcp":
        run_tcp(cfg)
    else:
        print("module mode is for import only; choose tcp/stdout to run as a process.", file=sys.stderr)
        sys.exit(2)
