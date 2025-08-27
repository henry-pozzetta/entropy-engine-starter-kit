# North-Star User Journey (what we optimize)

1. Land on repo → **see one big Quickstart**.
2. Click once (Win/macOS) or paste one line (Linux) → **installer runs**.
3. Demo opens (generator + 3D UI) → **see the Arrow**.
4. Click “Record & Feedback” → **JSONL saved + prefilled issue link opens**.
5. Join Discussions → **post results / keep collaborating**.

---

# Workstream A — Installers & “One-Click” Launch

## A1. Release artifacts (matrix builds)

* Package the app 3 ways so users pick what works:

  * **Windows EXE** (PyInstaller)
  * **macOS app bundle** (PyInstaller; notarization optional)
  * **Linux AppImage** (PyInstaller)
  * **Fallback:** one-liner Python bootstrap (uv/pipx)
  * **Optional:** Docker image for headless replay

**Checklist**

* [ ] Add `pyproject.toml` (entry point: `ee_mvp:main`).
* [ ] Add `scripts/build_pyinstaller.spec` (single-file, console off if web UI).
* [ ] GH Actions workflow (see C1) builds `{win,mac,linux}` and uploads to Release.
* [ ] Name assets predictably: `ee-mvp-vX.Y.Z-win.exe`, `…-mac.zip`, `…-linux.AppImage`.

## A2. One-click/one-line installers (repo root)

* **Windows**: `Start-EE.ps1` (double-clickable)
* **macOS/Linux**: `start-ee.command` (double-clickable on mac) and `curl | bash` one-liner

**Windows `Start-EE.ps1` (template)**

```powershell
# Double-click to download latest release and run
param([switch]$Replay,[string]$Profile="jammy")
$repo = "henry-pozzetta/entropy-engine-starter-kit"
$rel  = (Invoke-RestMethod "https://api.github.com/repos/$repo/releases/latest")
$asset = $rel.assets | Where-Object name -match "ee-mvp-.*-win.exe" | Select-Object -First 1
$dest = "$PSScriptRoot\$($asset.name)"
if (!(Test-Path $dest)) { Invoke-WebRequest $asset.browser_download_url -OutFile $dest }
Start-Process -FilePath $dest -ArgumentList @("--profile",$Profile, ($Replay ? "--replay" : "")) -NoNewWindow
```

**macOS/Linux one-liner (README)**

```bash
curl -fsSL https://raw.githubusercontent.com/henry-pozzetta/entropy-engine-starter-kit/main/install.sh | bash
```

**`install.sh` (template)**

```bash
#!/usr/bin/env bash
set -e
REPO="henry-pozzetta/entropy-engine-starter-kit"
OS=$(uname -s)
TMP=$(mktemp -d)
if [[ "$OS" == "Darwin" ]]; then ASSET="ee-mvp-*-mac.zip"; OPEN="open"; elif [[ "$OS" == "Linux" ]]; then ASSET="ee-mvp-*-linux.AppImage"; OPEN=""; fi
URL=$(curl -s https://api.github.com/repos/$REPO/releases/latest | grep browser_download_url | grep "$ASSET" | cut -d '"' -f 4)
cd "$TMP"
curl -L "$URL" -o app.bin
chmod +x app.bin
./app.bin --profile jammy || $OPEN app.bin
```

## A3. Python fallback installer (no admin rights)

* **Goal:** if binaries fail, a one-liner sets up a local venv and runs.

**README one-liner**

```bash
# universal fallback (uses uv if present, else python -m venv)
python - <<'PY'
import os,subprocess,sys,shutil
venv=".ee-venv"
if not shutil.which("python"): raise SystemExit("Python not found")
if not os.path.exists(venv): subprocess.check_call([sys.executable,"-m","venv",venv])
pip=os.path.join(venv,"Scripts" if os.name=="nt" else "bin","pip")
subprocess.check_call([pip,"install","-U","pip","-r","requirements.txt"])
exe=os.path.join(venv,"Scripts" if os.name=="nt" else "bin","python")
subprocess.check_call([exe,"ee_mvp.py","--profile","jammy"])
PY
```

## A4. Docker (optional, for replay demos)

* Build `Dockerfile` that serves the **web UI** on `:8050` and replays a sample trace:

```
docker run -p 8050:8050 ghcr.io/<owner>/ee-mvp:latest --replay docs/traces/jammy.jsonl
```

---

# Workstream B — App UX: Quickstart, Feedback, Privacy

## B1. Quickstart landing (README top)

* **Three big options** with badges:

  1. Windows: **Download & Run**
  2. macOS/Linux: **One-Line Install**
  3. Python users: **pip/uv Quickstart**
* One screenshot/GIF with labeled axes.

## B2. In-app **Feedback mode**

* `--feedback` flag adds two buttons in the UI:

  * **Record 60s & Save Feedback** → writes `evaluation.jsonl`
  * **Open Prefilled Issue** → launches browser to GitHub Discussions/Issue template with query params:

    * OS, approx FPS, profile, helpful (Y/N), clarity (1–5)
* No network writes by default; user reviews JSON before submitting.

## B3. Privacy note (README)

* “No telemetry leaves your machine unless you click ‘Open Prefilled Issue’.”
* “Feedback file contents:” (show the tiny JSON schema).

## B4. Troubleshooting cheatsheet

* WebGL/driver notes, port conflicts, “flat visuals? try `--viz_y_gain 1.6 --viz_z_gain 2.0`”.

---

# Workstream C — CI/CD: Build, Test, Release Automation

## C1. GitHub Actions `release.yml`

* Triggers on tag `v*`.
* Matrix `{windows-latest, macos-latest, ubuntu-latest}`:

  * checkout → set up Python → install → unit tests (TTL, idempotency, geometry) → PyInstaller build → upload Release asset.
* Also build **Docker** and push to GHCR (optional).

**Skeleton**

```yaml
name: release
on:
  push: { tags: ['v*'] }
jobs:
  build:
    runs-on: ${{ matrix.os }}
    strategy:
      matrix: { os: [ubuntu-latest, macos-latest, windows-latest] }
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with: { python-version: '3.11' }
      - run: pip install -r requirements.txt pyinstaller
      - run: pytest -q
      - run: pyinstaller scripts/build_pyinstaller.spec
      - uses: softprops/action-gh-release@v2
        with:
          files: dist/**/*
```

## C2. Pre-release smoke on PRs

* Lint, unit tests, headless replay test (ensures CLI works).
* On `main`, draft release notes.

## C3. Versioning & changelog

* `bumpversion` or a simple `scripts/tag_release.py` that updates `CHANGELOG.md`, creates a tag, pushes.

---

# Workstream D — Repo Hygiene & Community

## D1. Repo structure (top)

```
README.md
docs/
  ROADMAP.md
  QUICKSTART.md        # copy of README quickstart
  CLI_GUIDE.md         # flags & examples (Windows/macOS/Linux)
  PRIVACY.md
  TROUBLESHOOTING.md
  SCREENSHOTS/
  traces/              # small sample .jsonl
.github/
  ISSUE_TEMPLATE/{bug.yml,feature.yml,feedback.yml}
  workflows/{ci.yml,release.yml}
  DISCUSSION_TEMPLATE.md
  CODEOWNERS
CHANGELOG.md
```

## D2. GitHub Discussions & labels

* Enable Discussions categories: `Announcements`, `Install-Help`, `Results`, `Dev`.
* Labels: `feature`, `perf`, `docs`, `ux`, `good-first-issue`, `help-wanted`.
* Project board: “EE MVP Release Train” with 4 columns (To do / In progress / Review / Done).

## D3. Templates

* **Issues**: bug, feature, feedback (includes box to paste `evaluation.jsonl`).
* **PR template**: checklist (tests pass, docs updated, screenshot of UI).
* **CONTRIBUTING.md**: how to run tests, style, how to cut a release.

---

# Workstream E — App Internals (to support smooth installs)

## E1. Self-check command

* `ee_mvp.py --self-check` prints:

  * Python version, deps, port availability, GUI backend, WebGL OK?, sample CSV load OK.
* The installers run this first and show green checks.

## E2. Defaults that just work

* Default profile `jammy`.
* Default **web UI** port `8050` with `--auto-bump-ports`.
* If TCP source missing → auto-start demo generator child process.

## E3. Stable CLI

* Flags: `--source {demo|tcp|csv|replay}`, `--profile {...}`, `--fps`, `--trail-seconds`, `--viz_y_gain`, `--viz_z_gain`, `--feedback`.
* `--replay path.jsonl` always works even without GPU/browser (server-side render acceptable).

---

# Two-Week Execution Timeline (agile, small PRs)

**Week 1**

* Day 1–2: A1 matrix build (PyInstaller) + C1 release workflow → tag `v0.1.0-installers`.
* Day 3: A2 Start-EE scripts + A3 Python fallback → `v0.1.1`.
* Day 4: B1 Quickstart + B4 Troubleshooting → `v0.1.2`.
* Day 5: D2 labels/discussions + D3 templates → `v0.1.3`.

**Week 2**

* Day 6–7: B2 Feedback UI + JSONL + prefilled issue link → `v0.2.0-feedback`.
* Day 8: E1 Self-check; E2 sane defaults → `v0.2.1`.
* Day 9: C2 PR smoke tests; D1 docs set → `v0.2.2`.
* Day 10: Optional Docker, sample traces, polish → `v0.3.0`.

*(This builds on your earlier feature train; adjust tags to your roadmap.)*

---

# Definition of Ready (DOR) before you announce

* ✅ Latest Release has **Win/mac/Linux** artifacts + **Quickstart** GIF.
* ✅ “Start” scripts present (PS1 + `.command` + one-liner) and tested on clean VMs.
* ✅ README top section has three big run options + **privacy note**.
* ✅ Feedback flow creates `evaluation.jsonl` and opens prefilled issue.
* ✅ Discussions enabled; labels & templates live; roadmap linked.

---

# Smoke Test Script (run on fresh VM per OS)

1. Download/run one-click installer.
2. See Arrow within 30s.
3. Switch profile to `busy`; adjust gains; observe change.
4. Run `--feedback` for 20s; save JSONL; open prefilled issue.
5. Close app; re-launch via replay mode; confirm deterministic path.

If any step fails, open a blocking issue tagged `install-blocker`.

