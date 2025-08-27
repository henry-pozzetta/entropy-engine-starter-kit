# Entropy Engine MVP – Evaluation Kit

See the **shape of chaos** in your data stream. This one-click kit spins up:
- a test data stream generator (TCP),
- the Entropy Engine MVP (entropy level H~, slope Y, curvature Z),
- a 3D, rotatable browser view.

## Quickstart (Windows/macOS/Linux)
<a id="quickstart"></a>

[EE MVP PoC Demo — CLI User Guide](docs/CLI_GUIDE.md)

**Roadmap**: We’re iterating in small, tagged releases. See **[docs/ROADMAP.md](docs/ROADMAP.md)**.

# Entropy Engine MVP — TimeFund Edition

[![Release](https://img.shields.io/github/v/release/OWNER/REPO?label=release)](https://github.com/OWNER/REPO/releases)
[![Build](https://img.shields.io/github/actions/workflow/status/OWNER/REPO/ci.yml?label=ci)](https://github.com/OWNER/REPO/actions)
[![License](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)
[![Checksums](https://img.shields.io/badge/download-checksums-blue)](https://github.com/OWNER/REPO/releases/latest)

> **Donate time, not money.** Spend 30–60 minutes to install, run, and tell us if a live **Arrow of Information Entropy** helps you *see disorder early*.

![Arrow of Information Entropy — labeled axes](docs/img/arrow-hero.gif)

### Quickstart (pick your OS)

**Windows**  
1. Download `EE-MVP-Setup.exe` from the [latest release](https://github.com/OWNER/REPO/releases/latest)  
2. Double-click → Run “Calm” profile  
3. See the Arrow move → Done

**macOS**  
1. Download `.dmg` → drag app to Applications  
2. Open app → allow Gatekeeper if prompted  
3. Select a profile and watch the Arrow

**Linux**  
1. `chmod +x EE-MVP.AppImage && ./EE-MVP.AppImage`  
2. Pick a profile → watch the Arrow

> **Privacy Promise:** Offline by default. **No telemetry** leaves your machine unless you click **Submit Results**.  
> **If it looks flat:** try `--viz-y-gain 1.8 --viz-z-gain 2.2`. **If it stutters:** try `--fps 20` or **Replay** a sample.

### What you’ll see (10 sec)
- **X:** normalized entropy \( \tilde H \)  
- **Y:** slope \( d\tilde H/dt \)  
- **Z:** curvature \( d^2\tilde H/dt^2 \)  
- **Color:** volatility intensity

### Share results (30 sec)
- Click **Generate evaluation.jsonl** in the app, then post it in **[Discussions → Results](https://github.com/OWNER/REPO/discussions/new?category=results)**  
- Or fill the short web form (link)

**Roadmap:** [docs/ROADMAP.md](docs/ROADMAP.md) • **Changelog:** [CHANGELOG.md](CHANGELOG.md) • **Troubleshooting:** [docs/troubleshooting.md](docs/troubleshooting.md)  
**Code of Conduct:** [CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md) • **Security:** [SECURITY.md](SECURITY.md)

## Table of Contents
- [Quickstart](#quickstart)
