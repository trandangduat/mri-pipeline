param(
    [string]$ProjectRoot = (Split-Path $PSScriptRoot | Split-Path)
)

$ErrorActionPreference = "Stop"

Write-Host "=== Building neuroflow-backend.exe (one-dir) ===" -ForegroundColor Cyan

$specPath = Join-Path $PSScriptRoot "neuroflow-backend.spec"
$venvPython = Join-Path (Join-Path (Join-Path $ProjectRoot ".venv") "Scripts") "python.exe"

if (Test-Path $venvPython) {
    $python = $venvPython
} else {
    $python = "python"
}

Write-Host "Using Python: $python"

# Install PyInstaller if needed
& cmd.exe /c "`"$python`" -m PyInstaller --version >nul 2>nul"
if ($LASTEXITCODE -ne 0) {
    Write-Host "Installing PyInstaller..."
    & $python -m pip install pyinstaller --quiet
}

# Install project dependencies
Write-Host "Installing project dependencies..."
& $python -m pip install -r (Join-Path $ProjectRoot "requirements.txt") --quiet

# Run PyInstaller
Write-Host "Running PyInstaller..."
& $python -m PyInstaller $specPath --noconfirm --clean --distpath (Join-Path $ProjectRoot "dist") --workpath (Join-Path $ProjectRoot "build")

if ($LASTEXITCODE -ne 0) {
    Write-Error "PyInstaller build failed."
    exit 1
}

$outputDir = Join-Path (Join-Path $ProjectRoot "dist") "neuroflow-backend"
$exePath = Join-Path $outputDir "neuroflow-backend.exe"

if (Test-Path $exePath) {
    Write-Host "Build succeeded: $exePath" -ForegroundColor Green
} else {
    Write-Error "Expected output not found: $exePath"
    exit 1
}

# PyInstaller 6 one-directory builds keep all declared data in _internal.
# Inspect the real output before Tauri copies it, rather than relying only on
# the source spec to prove that the resource-root contract was assembled.
$internalRoot = Join-Path $outputDir "_internal"
$requiredResources = @(
    (Join-Path $internalRoot "normalize_volumes.py"),
    (Join-Path $internalRoot "pipeline\job_worker.py"),
    (Join-Path $internalRoot "info\subcortical_volume_feats.txt"),
    (Join-Path $internalRoot "configs\neuroflow")
)
foreach ($requiredResource in $requiredResources) {
    if (-not (Test-Path $requiredResource)) {
        Write-Error "Bundled backend is missing required _internal resource: $requiredResource"
        exit 1
    }
}

Write-Host "Checking bundled backend capabilities..."
$smokePort = 18765
$smokeToken = [guid]::NewGuid().ToString("N") + [guid]::NewGuid().ToString("N")
$previousSmokeToken = $env:NEUROFLOW_API_TOKEN
$backend = $null
try {
    # Start-Process inherits this build-only token. Restore the parent
    # environment immediately so it cannot affect a later developer launch.
    $env:NEUROFLOW_API_TOKEN = $smokeToken
    $backend = Start-Process -FilePath $exePath -ArgumentList @("server", "--host", "127.0.0.1", "--port", "$smokePort") -PassThru -WindowStyle Hidden
} finally {
    if ($null -eq $previousSmokeToken) {
        Remove-Item Env:NEUROFLOW_API_TOKEN -ErrorAction SilentlyContinue
    } else {
        $env:NEUROFLOW_API_TOKEN = $previousSmokeToken
    }
}
try {
    $capabilities = $null
    for ($attempt = 0; $attempt -lt 20; $attempt++) {
        try {
            $capabilities = Invoke-RestMethod -Uri "http://127.0.0.1:$smokePort/capabilities/runtime" -Headers @{ Authorization = "Bearer $smokeToken" } -TimeoutSec 2
            break
        } catch {
            Start-Sleep -Milliseconds 250
        }
    }
    if ($null -eq $capabilities -or -not $capabilities.ssh.ok) {
        throw "Bundled backend smoke test failed: Paramiko capability is unavailable."
    }
    $metadata = Invoke-RestMethod -Uri "http://127.0.0.1:$smokePort/metadata" -Headers @{ Authorization = "Bearer $smokeToken" } -TimeoutSec 2
    if ([string]$metadata.project_root -notlike "*_internal") {
        throw "Bundled backend smoke test failed: metadata did not resolve the PyInstaller _internal resource root."
    }

    $unauthenticatedStatus = 0
    try {
        Invoke-WebRequest -Uri "http://127.0.0.1:$smokePort/capabilities/runtime" -TimeoutSec 2 -ErrorAction Stop | Out-Null
    } catch {
        if ($_.Exception.Response) {
            $unauthenticatedStatus = [int]$_.Exception.Response.StatusCode
        }
    }
    if ($unauthenticatedStatus -ne 401) {
        throw "Bundled backend smoke test failed: /capabilities/runtime accepted a request without the launch token."
    }
} finally {
    if ($null -ne $backend -and -not $backend.HasExited) { Stop-Process -Id $backend.Id -Force }
}
