
---

## H) `CONTRIBUTING.md`

```markdown
# Contributing

Thanks for helping evolve the Entropy Engine!

## How to contribute
1. **Try the demo** (`run-demo.py`). Post a screenshot of your 3D arrow.
2. File an **Issue** for bugs/ideas. Use the templates.
3. Fork → branch → PR with a clear description and reproduction steps.

## Experiments we love
- Different `--datatype` (123 | abc | sym | mix)
- Changing `--clock`, `--uf`, and comparing arrow shapes
- Your real telemetry (sanitized) via CSV

## Dev setup
```bash
python -m venv venv
source venv/bin/activate  # or .\venv\Scripts\Activate.ps1 on Windows
pip install -r requirements.txt
