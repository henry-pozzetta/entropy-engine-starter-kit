# EE MVP PoC Demo — CLI User Guide (Clean Draft vNext)

*Last updated: August 27, 2025*

This guide helps you run the Entropy Engine MVP/PoC demo quickly and confidently. It covers one‑command launch, manual options, visualization controls, and troubleshooting. It also clarifies what the 3D Arrow means so you can evaluate usefulness.

---

## 1) What this demo does
- Starts a **sample telemetry generator** (TCP) or replays a **CSV**.
- Runs the **Entropy Engine MVP viewer** that computes entropy level and derivatives and renders a **3D Arrow**.
- Opens a **local web UI** in your browser.

**Components**
- `run-demo.ps1` (Windows) / `run-demo.sh` (macOS/Linux): one‑command launcher
- `test_stream_gen.py`: sample TCP generator
- `ee_mvp.py`: MVP viewer & 3D visualization

**Privacy & Safety**
- No telemetry is uploaded anywhere. Everything runs locally.
- TTL/health checks exist in the MVP; stale or malformed inputs are safely ignored.

---

## 2) Quick Start (recommended)

### Windows (PowerShell)
```powershell
# Full demo: auto-create venv, install deps, start generator + UI, open browser
./run-demo.ps1 -AutoBumpPorts `
  -VizArrowMode cone -VizTail -VizArrowGain 1.4 -VizYG 2 -VizZG 4 -VizAspect "1,1,1.6"
```

### macOS / Linux (shell)
```bash
# Assuming Python is installed and run-demo.sh is executable
./run-demo.sh --auto-bump-ports \
  --viz_arrow_mode cone --viz_tail --viz_arrow_gain 1.4 \
  --viz_y_gain 2 --viz_z_gain 4 --viz_aspect 1,1,1.6
```

> **Tip:** If ports are in use, use the auto‑bump options (see below) or choose custom ports.

---

## 3) Source & Format matrix

| Source | Format | How to run | Notes |
|---|---|---|---|
| TCP | **plain** (one number per line) | Generator (`test_stream_gen.py --mode tcp --fmt plain`) → Viewer (`ee_mvp.py --source tcp`) | **Supported** today. |
| TCP | JSON | Generator can emit JSON (`--fmt json`) | **Not yet supported** by viewer; use `plain` for TCP. |
| File | CSV | `ee_mvp.py --source csv --path telemetry.csv` | CSV must contain a `value` column or a single first column of values. |

**CSV schema**
- Preferred header: `value`. If missing, the first column will be used.
- Values are parsed as floats if possible; otherwise a stable string‑to‑numeric mapping is applied.

---

## 4) One‑command demo launcher (Windows)

### Purpose
`run-demo.ps1` spins up everything for you:
- Ensures a Python virtual environment exists
- Installs/validates required packages
- Starts the generator (TCP) and the MVP viewer (web UI)
- Opens your browser to the UI

### Syntax (common flags)
```powershell
./run-demo.ps1 \
  [-GenPort <int>]        # generator TCP port (default: 9009) \
  [-BindHost <string>]    # generator bind host (default: 127.0.0.1) \
  [-UiPort <int>]         # UI web port (default: 8050) \
  [-UiHost <string>]      # UI host interface (default: 127.0.0.1) \
  [-AutoBumpPorts]        # if port busy, auto-increment to next free \
  [-NoBrowser]            # start UI but don’t auto-open browser \
  [-Stop]                 # stop processes previously launched by the script

# Visualization tuning (passed through to ee_mvp.py)
  [-VizArrowMode <quiver|cone>]   # 3D arrow style (default: cone) \
  [-VizTail]                      # draw trajectory tail \
  [-VizArrowGain <float>]         # arrow length scale (default: 1.0) \
  [-VizYG <float>]                # Y (slope) visual gain (default: 1.0) \
  [-VizZG <float>]                # Z (curvature) visual gain (default: 1.0) \
  [-VizAspect "<x,y,z>"]         # axis aspect ratio, e.g. "1,1,1.6"

# Generator tuning (for test_stream_gen.py)
  [-DataType <123|abc|sym|mix>]   # symbol alphabet (default: 123) \
  [-Clock <float>]                # seconds per tick (default: 1.0) \
  [-RunTime <int>]                # seconds to run (0 = infinite) \
  [-UF <float>]                   # uncertainty factor 0..1 (default: 0.2) \
  [-Seed <int>]                   # RNG seed (optional)
```

### Quick starts
```powershell
# Vanilla demo (ports 9009 & 8050)
./run-demo.ps1

# Auto-bump if ports busy; stronger Z perspective
./run-demo.ps1 -AutoBumpPorts -VizArrowMode cone -VizTail -VizArrowGain 1.4 -VizYG 2 -VizZG 4 -VizAspect "1,1,1.6"

# Use different ports (e.g., restricted workspace)
./run-demo.ps1 -GenPort 9109 -UiPort 8060 -AutoBumpPorts

# Stop everything started by the script
./run-demo.ps1 -Stop
```

**Auto‑bump behavior**
- The launcher attempts the **next available port(s)** when the requested port is in use.
- The MVP UI also auto‑tries up to **5** consecutive ports internally.

**Stop semantics**
- `-Stop` terminates processes **launched by the most recent run** of the script (tracked by PID).
- If you started components manually, close those shells/windows or stop by port.

**Security note (bind host)**
- Prefer `127.0.0.1` for `-BindHost`/`-UiHost` on untrusted networks.
- Use `0.0.0.0` only when you intentionally need remote access on your LAN.

---

## 5) Sample telemetry generator (`test_stream_gen.py`)

### Purpose
Emit a predictable but configurable **one value per tick** stream over TCP for the viewer.

### Usage
```powershell
# Windows venv invocation shown; adapt `python` path for macOS/Linux
./venv/Scripts/python.exe ./test_stream_gen.py \
  --mode tcp \
  --datatype {123|abc|sym|mix} \
  --clock <seconds> \
  --runtime <seconds>        # 0 = run forever \
  --uf <0..1>                # randomness injection \
  --seed <int>               # RNG seed (optional) \
  --host <bind-host>         # default 127.0.0.1 \
  --port <bind-port>         # default 9009 \
  --fmt {plain|json}         # default plain
```

### Meaning of key parameters
- `--datatype` — token alphabet
  - `123`: numeric tokens (baseline for continuous distributions)
  - `abc`: alphabetic tokens
  - `sym`: symbolic charset (non‑alnum)
  - `mix`: mixed alphabet (highest combinatorial richness)
- `--clock` — seconds per output sample (e.g., `0.25` = 4 Hz)
- `--runtime` — total run time in seconds (`0` = until stopped)
- `--uf` — **Uncertainty Factor** (entropy nudge) `0.0`…`1.0`
  - `0.0` = fully predictable; `1.0` = highly random
- `--fmt` — use `plain` for compatibility with the viewer’s TCP source today

### Examples
```powershell
# Numeric tokens, 4 Hz, infinite, moderate uncertainty
./venv/Scripts/python.exe ./test_stream_gen.py --mode tcp --datatype 123 --clock 0.25 --runtime 0 --uf 0.2 --seed 42 --host 127.0.0.1 --port 9009 --fmt plain

# Mixed alphabet, slower tick, finite run on a different port
./venv/Scripts/python.exe ./test_stream_gen.py --mode tcp --datatype mix --clock 1.0 --runtime 300 --uf 0.35 --port 9109 --fmt plain
```

---

## 6) MVP viewer (`ee_mvp.py`)

### Purpose
Ingest the stream → compute **H̃ (level)**, **dH/dt (slope)**, **d²H/dt² (curvature)** → render a rotatable **3D Arrow** with optional tail.

### Usage
```bash
python ee_mvp.py \
  --source {tcp|csv} \
  # TCP source:
  --tcp_host <host> --tcp_port <port> \
  # CSV source:
  --path <telemetry.csv> \
  # Clock/analysis
  --dt <seconds-per-tick>         # e.g., 0.25 (also CSV replay step) \
  --bins <int>                    # histogram bins (e.g., 24) \
  --window <seconds>              # entropy window length (e.g., 180) \
  --alpha <0..1>                  # EWMA smoothing for H̃ (optional; default 0.2) \
  --Tstar <float>                 # reserved/experimental (note: may become --tstar) \
  # Web UI
  --ui_host <host>                # default 127.0.0.1 \
  --ui_port <port>                # default 8050 \
  # Visualization
  --viz_arrow_mode {quiver|cone}  # default cone \
  --viz_tail \
  --viz_arrow_gain <float>        # arrow length scale \
  --viz_y_gain <float>            # Y (slope) visual gain \
  --viz_z_gain <float>            # Z (curvature) visual gain \
  --viz_aspect x,y,z              # axis ratio, e.g., 1,1,1.6
```

### Common runs
```bash
# Read from running TCP generator on 127.0.0.1:9009
python ee_mvp.py --source tcp --tcp_host 127.0.0.1 --tcp_port 9009 \
  --dt 0.25 --bins 24 --window 180 --alpha 0.2 --Tstar 0 \
  --ui_host 127.0.0.1 --ui_port 8050 \
  --viz_arrow_mode cone --viz_tail --viz_arrow_gain 1.4 --viz_y_gain 2 --viz_z_gain 4 --viz_aspect 1,1,1.6

# From a CSV file instead of TCP
python ee_mvp.py --source csv --path ./telemetry.csv \
  --dt 0.5 --bins 32 --window 240 --viz_arrow_mode cone
```

**Note on `--Tstar`**
- The current flag in code is `--Tstar`. In a future release we may rename to `--tstar` to align with lowercase flag style.

---

## 7) Visualization: axes, gains & “flatness”
- **X = H̃(X)** ∈ **[0,1]** after normalization
- **Y = dH/dt**, **Z = d²H/dt²** can be larger in magnitude → the plot can look **flat** along X

**Make it pop**
- Increase `--viz_y_gain` (slope) and `--viz_z_gain` (curvature)
- Increase `--viz_arrow_gain` for overall vector length
- Use `--viz_aspect 1,1,1.6` to deepen the Z perspective

**Distance (optional interpretation)**
- The instantaneous intensity can be summarized as `|v| = sqrt(X² + Y² + Z²)` and mapped to color.

---

## 8) Manual flow (advanced)
```powershell
# 1) Start generator on an alternate port
./venv/Scripts/python.exe ./test_stream_gen.py --mode tcp --datatype 123 --clock 0.25 --uf 0.2 --port 9109 --fmt plain

# 2) Start MVP pointing at that port
python ee_mvp.py --source tcp --tcp_host 127.0.0.1 --tcp_port 9109 \
  --dt 0.25 --bins 24 --window 180 --ui_port 8060 \
  --viz_arrow_mode cone --viz_tail --viz_arrow_gain 1.4 --viz_y_gain 2 --viz_z_gain 4 --viz_aspect 1,1,1.6
```

---

## 9) Troubleshooting quick hits
- **Browser didn’t open**
  - Open manually: `http://127.0.0.1:<UiPort>` (default 8050)
  - Add `-NoBrowser` to the demo script if you prefer manual navigation
- **Port in use (TCP or UI)**
  - Use `-AutoBumpPorts` (launcher) or try unused ports: `-GenPort 9109 -UiPort 8060`
  - Check listeners: `netstat -ano -p tcp | findstr :<port>` (Windows) or `lsof -i :<port>` (mac/Linux)
- **PermissionError: [WinError 10013]** on generator bind
  - Try `--host 0.0.0.0` *only* on trusted networks, or switch to another port
  - Ensure antivirus/firewall allows Python on that port
- **Missing Python packages**
  - Install: `python -m pip install -r requirements.txt`
  - Sanity check:
    ```powershell
    python -c "import importlib.util as u;mods=['numpy','plotly','dash'];print('OK' if all(u.find_spec(m) for m in mods) else 'MISSING')"
    ```
- **Looks too flat**
  - Try `--viz_y_gain 2 --viz_z_gain 4 --viz_arrow_gain 1.4 --viz_aspect 1,1,1.6`
- **Stop everything**
  - If you used the demo script: `./run-demo.ps1 -Stop`
  - Otherwise: close the app shells or kill by port

---

## 10) Flag mapping: Launcher ↔ Viewer
| PowerShell flag | Viewer flag (ee_mvp.py) | Meaning |
|---|---|---|
| `-VizArrowMode` | `--viz_arrow_mode` | Arrow style (`cone` recommended) |
| `-VizTail` | `--viz_tail` | Draw trajectory tail |
| `-VizArrowGain` | `--viz_arrow_gain` | Overall vector length scale |
| `-VizYG` | `--viz_y_gain` | Slope (Y) visual gain |
| `-VizZG` | `--viz_z_gain` | Curvature (Z) visual gain |
| `-VizAspect` | `--viz_aspect` | Axis aspect ratios `x,y,z` |

---

## 11) Appendix — Defaults & ports
- **Generator**: `127.0.0.1:9009`
- **Web UI**: `127.0.0.1:8050`
- **Analysis**: `--dt 0.25`, `--bins 24`, `--window 180`, `--alpha 0.2`
- **Viz**: `--viz_arrow_mode cone`, `--viz_y_gain 1.0`, `--viz_z_gain 1.0`, `--viz_arrow_gain 1.0`

---

**That’s it.** You should get a crisp 3D Arrow that reflects **H̃ (level)**, **slope**, and **curvature** over time. If your plot feels flat, tweak the gains; if it stutters, reduce FPS or switch to CSV replay. For issues, open a GitHub Discussion in **Install‑Help** or file a bug with your OS, steps, and a screenshot.

