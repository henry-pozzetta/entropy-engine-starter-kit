<# ======================================================================
  Entropy Engine MVP – demo launcher (Windows PowerShell)
  - Creates/uses .\venv
  - Installs requirements when missing
  - Starts test_stream_gen.py (TCP) and ee_mvp.py (Dash)
  - Waits for UI to be healthy, then opens browser
  - Tracks PIDs for clean shutdown

  Usage (defaults):
    .\run-demo.ps1

  Examples:
    .\run-demo.ps1 -GenPort 9109 -UiPort 8060 -AutoBumpPorts `
      -VizArrowMode cone -VizTail -VizArrowGain 1.4 -VizYG 2 -VizZG 4 -VizAspect "1,1,1.6"

  Stop processes:
    .\run-demo.ps1 -Stop
====================================================================== #>

[CmdletBinding()]
param(
  # ---- Generator knobs ----
  [int]    $GenPort      = 9109,            # TCP port to listen on
  [string] $GenHost      = "127.0.0.1",
  [ValidateSet("123","abc","sym","mix")]
  [string] $Datatype     = "123",
  [double] $Clock        = 0.25,            # seconds per tick
  [int]    $Runtime      = 0,               # 0 = run until stopped
  [double] $Uf           = 0.2,             # unexpected factor 0..1
  [int]    $Seed         = 42,
  [ValidateSet("plain","json")]
  [string] $Fmt          = "plain",

  # ---- MVP knobs ----
  [double] $Dt           = 0.25,
  [int]    $Bins         = 24,
  [double] $Window       = 180,
  [double] $Alpha        = 0.2,
  [double] $Tstar        = 0.0,

  # ---- UI (Dash) ----
  [string] $UiHost       = "127.0.0.1",
  [int]    $UiPort       = 8050,

  # ---- Visualization tuning (visual-only) ----
  [switch] $VizTail,
  [ValidateSet("cone","line")]
  [string] $VizArrowMode = "cone",
  [double] $VizArrowGain = 1.0,
  [double] $VizYG        = 1.0,             # Y gain
  [double] $VizZG        = 1.0,             # Z gain
  [string] $VizAspect    = "auto",          # "x,y,z" or "auto"
  [double] $VizConeSizeRef = 0.6,
  [ValidateSet("absolute","scaled")]
  [string] $VizConeSizeMode = "absolute",

  # ---- Behavior ----
  [switch] $AutoBumpPorts,                  # auto-try next ports if in use (Gen/UI)
  [int]    $MaxPortAttempts = 5,
  [switch] $Stop                                # kill previously spawned generator/UI PIDs
)

# --- Helpers -------------------------------------------------------------

function Write-Info  { param([string]$m) Write-Host "[demo] $m" -ForegroundColor Cyan }
function Write-Ok    { param([string]$m) Write-Host "[demo] $m" -ForegroundColor Green }
function Write-Warn  { param([string]$m) Write-Host "[demo] $m" -ForegroundColor Yellow }
function Write-Err   { param([string]$m) Write-Host "[demo] $m" -ForegroundColor Red }

$Here = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $Here

$VenvPy = Join-Path $Here "venv\Scripts\python.exe"
$ReqTxt = Join-Path $Here "requirements.txt"
$GenPy  = Join-Path $Here "test_stream_gen.py"
$MvpPy  = Join-Path $Here "ee_mvp.py"
$PidFile= Join-Path $Here ".demo_pids.json"

function Get-PortOwner {
  param([int]$Port)
  $lines = netstat -ano -p tcp | Select-String ":$Port"
  if (-not $lines) { return $null }
  foreach ($line in $lines) {
    $tokens = $line.ToString() -split '\s+'
    if ($tokens.Length -ge 5 -and $tokens[-1] -match '^\d+$') {
      return [int]$tokens[-1]
    }
  }
  return $null
}

function Test-PortFree {
  param([int]$Port)
  return -not (Get-PortOwner -Port $Port)
}

function Ensure-Venv {
  if (-not (Test-Path $VenvPy)) {
    Write-Info "creating venv …"
    & python -m venv "$Here\venv"
    if ($LASTEXITCODE -ne 0 -or -not (Test-Path $VenvPy)) {
      Write-Err "failed to create venv; ensure Python is installed and on PATH."
      exit 1
    }
  }
}

function Ensure-Requirements {
  Write-Info "installing requirements …"
  & $VenvPy -m pip --version | Out-Null
  if ($LASTEXITCODE -ne 0) {
    Write-Err "pip not available in venv"
    exit 1
  }
  & $VenvPy -m pip install --upgrade pip | Out-Null
  if (Test-Path $ReqTxt) {
    & $VenvPy -m pip install -r $ReqTxt
  } else {
    & $VenvPy -m pip install numpy pandas plotly dash
  }
  if ($LASTEXITCODE -ne 0) {
    Write-Err "pip install failed"
    exit 1
  }
}

function Start-Generator {
  param([int]$Port,[string]$GenHostParam)

  if (-not (Test-Path $GenPy)) { Write-Err "missing $GenPy"; exit 1 }

  $attempt = 0
  $usePort = $Port
  while ($true) {
    if (Test-PortFree -Port $usePort) { break }
    if (-not $AutoBumpPorts -or $attempt -ge $MaxPortAttempts) {
      $pid = Get-PortOwner -Port $usePort
      Write-Err "GenPort $usePort is in use (PID=$pid). Use -GenPort or -AutoBumpPorts."
      exit 1
    }
    $attempt++
    $usePort++
    Write-Warn "GenPort in use; trying $usePort …"
  }

  $args = @(
    $GenPy, "--mode","tcp",
    "--datatype", $Datatype,
    "--clock",    "$Clock",
    "--runtime",  "$Runtime",
    "--uf",       "$Uf",
    "--seed",     "$Seed",
    "--host",     $GenHostParam,
    "--port",     "$usePort",
    "--fmt",      $Fmt
  )

  Write-Info "starting generator on $($GenHostParam):$usePort …"
  $p = Start-Process -PassThru -WindowStyle Minimized -FilePath $VenvPy -ArgumentList $args
  if (-not $p) { Write-Err "failed to start generator"; exit 1 }
  return @{ PID = $p.Id; Port = $usePort }
}

function Start-MVP {
  param([int]$GenPortUsed,[int]$UiPortWanted)

  if (-not (Test-Path $MvpPy)) { Write-Err "missing $MvpPy"; exit 1 }

  $attempt = 0
  $ui = $UiPortWanted
  while ($true) {
    if (Test-PortFree -Port $ui) { break }
    if (-not $AutoBumpPorts -or $attempt -ge $MaxPortAttempts) {
      $pid = Get-PortOwner -Port $ui
      Write-Err "UiPort $ui is in use (PID=$pid). Use -UiPort or -AutoBumpPorts."
      exit 1
    }
    $attempt++
    $ui++
    Write-Warn "UiPort in use; trying $ui …"
  }

  $vizTailArg = $null
  if ($VizTail) { $vizTailArg = "--viz_tail" }

  $args = @(
    $MvpPy,
    "--source","tcp",
    "--tcp_host",$GenHost,
    "--tcp_port","$GenPortUsed",
    "--dt","$Dt","--bins","$Bins","--window","$Window","--alpha","$Alpha","--Tstar","$Tstar",
    "--ui_host",$UiHost,"--ui_port","$ui",
    "--viz_arrow_mode",$VizArrowMode,
    "--viz_arrow_gain","$VizArrowGain",
    "--viz_y_gain","$VizYG",
    "--viz_z_gain","$VizZG",
    "--viz_aspect",$VizAspect,
    "--viz_cone_sizeref","$VizConeSizeRef",
    "--viz_cone_sizemode",$VizConeSizeMode
  )
  if ($vizTailArg) { $args += $vizTailArg }

  Write-Info "starting MVP (UI $($UiHost):$ui, gen port $GenPortUsed) …"
  $p = Start-Process -PassThru -WindowStyle Normal -FilePath $VenvPy -ArgumentList $args
  if (-not $p) { Write-Err "failed to start MVP"; exit 1 }

  return @{ PID = $p.Id; UiPort = $ui }
}

function Wait-UiAndOpen {
  param([string]$Url,[int]$MaxTries = 40,[int]$DelayMs = 250)
  Write-Info "waiting for UI $Url …"
  for ($i=0; $i -lt $MaxTries; $i++) {
    try {
      Invoke-WebRequest -UseBasicParsing -TimeoutSec 2 -Uri $Url | Out-Null
      Start-Process $Url | Out-Null
      Write-Ok "UI is ready → $Url"
      return $true
    } catch {
      Start-Sleep -Milliseconds $DelayMs
    }
  }
  Write-Warn "UI not reachable yet (you can open $Url manually when it’s up)."
  return $false
}

function Save-PIDs {
  param([int]$GenPID,[int]$MvpPID,[int]$GenPortUsed,[int]$UiPortUsed)
  $obj = [ordered]@{
    generator_pid = $GenPID
    mvp_pid       = $MvpPID
    gen_port      = $GenPortUsed
    ui_port       = $UiPortUsed
    saved_at      = (Get-Date).ToString("s")
  }
  $obj | ConvertTo-Json | Set-Content -Encoding UTF8 $PidFile
}

function Stop-Previous {
  if (-not (Test-Path $PidFile)) {
    Write-Warn "no .demo_pids.json found; nothing to stop."
    return
  }
  $state = Get-Content $PidFile | ConvertFrom-Json
  $pids = @()
  if ($state.generator_pid) { $pids += [int]$state.generator_pid }
  if ($state.mvp_pid)       { $pids += [int]$state.mvp_pid }
  if ($pids.Count -eq 0) {
    Write-Warn "no PIDs recorded."
    return
  }
  foreach ($pid in $pids) {
    try {
      Write-Info "stopping PID $pid …"
      Stop-Process -Id $pid -Force -ErrorAction Stop
    } catch {
      Write-Warn "could not stop PID $pid (may already be closed)"
    }
  }
  Remove-Item -ErrorAction SilentlyContinue $PidFile
  Write-Ok "stopped recorded demo processes."
}

# --- Stop mode? ----------------------------------------------------------
if ($Stop) {
  Stop-Previous
  exit 0
}

# --- Main flow -----------------------------------------------------------

Write-Info "project: $Here"

Ensure-Venv
Ensure-Requirements

# Sanity check: can we import numpy/plotly?
# Sanity check: can we import numpy/plotly?
Write-Info "sanity import check …"
$pyCheck = @'
import sys, importlib, importlib.util

mods = ["numpy", "plotly"]
missing = [m for m in mods if importlib.util.find_spec(m) is None]

if missing:
    print("MISSING: " + ", ".join(missing))
    sys.exit(1)
else:
    print("OK")
    sys.exit(0)
'@

# Write to a temp file (safer than -c / here-doc in PowerShell), run, and clean up
$tmpPy = [System.IO.Path]::GetTempFileName().Replace(".tmp",".py")
[System.IO.File]::WriteAllText($tmpPy, $pyCheck, [System.Text.Encoding]::UTF8)

& $VenvPy $tmpPy
$code = $LASTEXITCODE

Remove-Item -ErrorAction SilentlyContinue $tmpPy

if ($code -ne 0) {
  Write-Err "Python packages missing. Try: `"$VenvPy`" -m pip install -r requirements.txt"
  exit 1
}


#Write-Info "sanity import check …"
#$pyOneLiner = @"
#import importlib, sys
#mods = ["numpy", "plotly"]
#missing = [m for m in mods if importlib.util.find_spec(m) is None]
#if missing:
#    print("MISSING: " + ", ".join(missing))
#    sys.exit(1)
#print("OK")
#"@
#$pyOneLiner = ($pyOneLiner -split "`r?`n" | Where-Object { $_ -ne "" }) -join "; "
#& $VenvPy -c $pyOneLiner
#if ($LASTEXITCODE -ne 0) {
#  Write-Err "Python packages missing. Try: `"$VenvPy`" -m pip install -r requirements.txt"
#  exit 1
#}

# Start generator (with port bump if asked)
$gen = Start-Generator -Port $GenPort -GenHostParam $GenHost
$genPid  = $gen.PID
$genPort = $gen.Port
Write-Ok "generator PID=$genPid on $($GenHost):$genPort"

Start-Sleep -Milliseconds 600  # small warmup

# Start MVP and wait for UI
$mvp = Start-MVP -GenPortUsed $genPort -UiPortWanted $UiPort
$mvpPid = $mvp.PID
$uiPort = $mvp.UiPort
Write-Ok "mvp PID=$mvpPid (UI port $uiPort)"

$uiUrl = "http://$($UiHost):$uiPort/"
Wait-UiAndOpen -Url $uiUrl | Out-Null

# Persist PIDs for Stop
Save-PIDs -GenPID $genPid -MvpPID $mvpPid -GenPortUsed $genPort -UiPortUsed $uiPort

Write-Ok "demo launched. Close windows or run '.\run-demo.ps1 -Stop' to shut down."
