$ErrorActionPreference = "Stop"
$here = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $here

# Optional: avoid policy issues for this shell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass -Force

#python .\run-demo.py
Write-Host "[demo] creating venv …"
if (-not (Test-Path "venv")) {
    python -m venv venv
}

Write-Host "[demo] installing requirements …"
.\venv\Scripts\python.exe -m pip install --upgrade pip
.\venv\Scripts\python.exe -m pip install -r requirements.txt

Write-Host "[demo] starting generator …"
Start-Process powershell -ArgumentList "-NoExit", "-Command", ".\venv\Scripts\python.exe .\test_stream_gen.py --mode tcp --datatype 123 --clock 0.25 --runtime 0 --uf 0.2 --host 127.0.0.1 --port 9009 --fmt plain"

Write-Host "[demo] opening http://127.0.0.1:8050/"
Start-Process "http://127.0.0.1:8050/"

Write-Host "[demo] starting MVP …"
Start-Process powershell -ArgumentList "-NoExit", "-Command", ".\venv\Scripts\python.exe .\ee_mvp.py --source tcp --tcp_host 127.0.0.1 --tcp_port 9009 --dt 0.25 --bins 24 --window 180"

Write-Host "[demo] demo launched! Close windows manually when done."
