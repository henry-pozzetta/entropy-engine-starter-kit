$ErrorActionPreference = "Stop"
$here = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $here

# Optional: avoid policy issues for this shell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass -Force

python .\run-demo.py
