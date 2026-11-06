param(
  [string] $ModelAllowlistFile = "",
  [int] $TaskRetentionMinutes = 0,
  [switch] $VisibleBrowser
)

$ErrorActionPreference = "Stop"

$root = Split-Path -Parent $MyInvocation.MyCommand.Path
$backend = Join-Path $root "backend"
$frontend = Join-Path $root "frontend"
$defaultModelAllowlistFile = Join-Path $root "demo-models.json"
if (-not $ModelAllowlistFile) {
  $ModelAllowlistFile = $defaultModelAllowlistFile
}
if (-not [System.IO.Path]::IsPathRooted($ModelAllowlistFile)) {
  $ModelAllowlistFile = Join-Path $root $ModelAllowlistFile
}
if (-not (Test-Path -LiteralPath $ModelAllowlistFile -PathType Leaf)) {
  throw "Model allowlist file not found: $ModelAllowlistFile"
}
$env:DEMO_ALLOWED_MODELS_FILE = (Resolve-Path -LiteralPath $ModelAllowlistFile).Path
$env:DEMO_SAFETY_GUARD = "0"
if ($VisibleBrowser) {
  $env:DEMO_BROWSER_HEADLESS = "0"
  $env:DEMO_BROWSER_STREAMING = "0"
  $env:VITE_BROWSER_STREAMING = "false"
} else {
  $env:DEMO_BROWSER_HEADLESS = "1"
  $env:DEMO_BROWSER_STREAMING = "1"
  $env:VITE_BROWSER_STREAMING = "true"
}
if ($TaskRetentionMinutes -lt 0) {
  throw "TaskRetentionMinutes must be zero or greater."
}
$env:DEMO_TASK_RETENTION_SECONDS = "$($TaskRetentionMinutes * 60)"
$backendUrl = "http://127.0.0.1:8000"
$frontendUrl = "http://127.0.0.1:5173"

Add-Type -AssemblyName System.Windows.Forms
$screen = [System.Windows.Forms.Screen]::PrimaryScreen.Bounds
$halfWidth = [Math]::Floor($screen.Width / 2)
$height = $screen.Height

# The automation browser occupies the right half of the primary display.
$env:DEMO_BROWSER_WIDTH = "$halfWidth"
$env:DEMO_BROWSER_HEIGHT = "$height"
$env:DEMO_BROWSER_LEFT = "$halfWidth"
$env:DEMO_BROWSER_TOP = "0"

Write-Host "Starting backend..."
$backendCommand = "Set-Location '$backend'; uv run uvicorn main:app --host 0.0.0.0 --port 8000"
$backendProcess = Start-Process powershell.exe `
  -ArgumentList "-NoExit", "-Command", $backendCommand `
  -PassThru

Write-Host "Starting frontend..."
$frontendCommand = "Set-Location '$frontend'; npm run dev -- --host 0.0.0.0"
$frontendProcess = Start-Process powershell.exe `
  -ArgumentList "-NoExit", "-Command", $frontendCommand `
  -PassThru

function Wait-ForUrl([string] $name, [string] $url, [int] $timeoutSeconds = 90) {
  $deadline = (Get-Date).AddSeconds($timeoutSeconds)
  do {
    if ($name -eq "backend" -and $backendProcess.HasExited) {
      throw "Backend process exited before $url became available. Check its PowerShell window."
    }
    if ($name -eq "frontend" -and $frontendProcess.HasExited) {
      throw "Frontend process exited before $url became available. Check its PowerShell window."
    }
    try {
      $response = Invoke-WebRequest -Uri $url -UseBasicParsing -TimeoutSec 2
      if ($response.StatusCode -ge 200 -and $response.StatusCode -lt 500) {
        return
      }
    } catch {
      Start-Sleep -Milliseconds 500
    }
  } while ((Get-Date) -lt $deadline)
  throw "Timed out waiting for $name at $url. Check the corresponding PowerShell window for startup errors."
}

function Stop-ProcessTree([int] $processId) {
  $children = @(Get-CimInstance Win32_Process -Filter "ParentProcessId = $processId")
  foreach ($child in $children) {
    Stop-ProcessTree $child.ProcessId
  }
  $process = Get-Process -Id $processId -ErrorAction SilentlyContinue
  if ($process) {
    Stop-Process -Id $processId -Force -ErrorAction SilentlyContinue
  }
}

Wait-ForUrl "backend" "$backendUrl/api/health"
Wait-ForUrl "frontend" $frontendUrl

$windowWidth = if ($VisibleBrowser) { $halfWidth } else { $screen.Width }
$browserArgs = "--new-window --app=$frontendUrl --window-position=0,0 --window-size=$windowWidth,$height"
$browser = Get-Command msedge.exe -ErrorAction SilentlyContinue
if (-not $browser) {
  $browser = Get-Command chrome.exe -ErrorAction SilentlyContinue
}
if ($browser) {
  if ($VisibleBrowser) {
    Start-Process $browser.Source -ArgumentList $browserArgs | Out-Null
  } else {
    $browserArgs = "--new-window --app=$frontendUrl --window-position=0,0 --window-size=$($screen.Width),$height"
    Start-Process $browser.Source -ArgumentList $browserArgs | Out-Null
  }
} else {
  Start-Process $frontendUrl
  Write-Warning "Could not find Edge or Chrome. Open $frontendUrl manually."
}

Write-Host ""
Write-Host "Demo is ready:"
if ($VisibleBrowser) {
  Write-Host "  Browser mode: visible split-screen"
  Write-Host "  Frontend: $frontendUrl (left half)"
} else {
  Write-Host "  Browser mode: headless live stream"
  Write-Host "  Frontend: $frontendUrl (browser preview shown in the right pane)"
}
Write-Host "  Backend:  $backendUrl"
Write-Host "  Models:   $ModelAllowlistFile"
if ($TaskRetentionMinutes -gt 0) {
  Write-Host "  Task retention: $TaskRetentionMinutes minute(s) for non-archived completed tasks"
} else {
  Write-Host "  Task retention: disabled"
}
if ($VisibleBrowser) {
  Write-Host "  Automation browser: right half when the first task starts"
}
Write-Host ""
Write-Host "Press Ctrl+C to stop the demo."

try {
  while ($true) {
    if ($backendProcess.HasExited -or $frontendProcess.HasExited) {
      Write-Warning "A demo process exited. Check its PowerShell window for details."
    }
    Start-Sleep -Seconds 2
  }
} finally {
  Stop-ProcessTree $backendProcess.Id
  Stop-ProcessTree $frontendProcess.Id
}
