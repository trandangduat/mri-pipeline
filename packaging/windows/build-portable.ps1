param(
    [string]$ProjectRoot = (Split-Path $PSScriptRoot | Split-Path)
)

$ErrorActionPreference = "Stop"

Write-Host "========================================" -ForegroundColor Cyan
Write-Host "  NeuroFlow Windows Portable Builder" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

if ($ProjectRoot.StartsWith("\\")) {
    Write-Error "ProjectRoot is a UNC path ($ProjectRoot). Tauri/npm Windows builds do not work reliably from \\wsl.localhost paths. Copy or clone this repo to a local Windows path such as C:\Users\ADMIN\mri-pipeline, then rerun this script there."
    exit 1
}

# --- Verify Windows ---
if (-not ($env:OS -eq "Windows_NT")) {
    Write-Warning "This script is designed for Windows. Proceeding anyway for CI/testing."
}

# --- Verify prerequisites ---
Write-Host "[1/6] Checking prerequisites..." -ForegroundColor Yellow

function Assert-Command {
    param([string]$Name, [string]$Install)
    if (-not (Get-Command $Name -ErrorAction SilentlyContinue)) {
        Write-Error "$Name is required but not found. $Install"
        exit 1
    }
    Write-Host "  OK: $Name"
}

function Stop-PortableProcesses {
    param([string]$PortableDir)

    if (-not ($env:OS -eq "Windows_NT")) {
        return
    }
    if (-not (Test-Path $PortableDir)) {
        return
    }

    $portableRoot = [System.IO.Path]::GetFullPath($PortableDir).TrimEnd('\') + '\'
    $processes = Get-CimInstance Win32_Process -ErrorAction SilentlyContinue | Where-Object {
        if (-not $_.ExecutablePath) {
            $false
        } else {
            $exePath = [System.IO.Path]::GetFullPath($_.ExecutablePath)
            $exePath.StartsWith($portableRoot, [System.StringComparison]::OrdinalIgnoreCase)
        }
    }

    foreach ($process in $processes) {
        Write-Host "  Stopping running portable process: $($process.Name) (PID $($process.ProcessId))"
        Stop-Process -Id $process.ProcessId -Force -ErrorAction SilentlyContinue
    }

    if ($processes) {
        Start-Sleep -Milliseconds 500
    }
}

Assert-Command "node" "Install Node.js from https://nodejs.org/"
Assert-Command "npm" "Install Node.js from https://nodejs.org/"
Assert-Command "cargo" "Install Rust from https://rustup.rs/"

    $venvPython = Join-Path (Join-Path (Join-Path $ProjectRoot ".venv") "Scripts") "python.exe"
if (Test-Path $venvPython) {
    $python = $venvPython
} else {
    Assert-Command "python" "Install Python from https://python.org/"
    $python = "python"
}
Write-Host "  OK: Python ($python)"

# Ensure PyInstaller is available
& cmd.exe /c "`"$python`" -m PyInstaller --version >nul 2>nul"
if ($LASTEXITCODE -ne 0) {
    Write-Host "  Installing PyInstaller..."
    & $python -m pip install pyinstaller --quiet
}
Write-Host "  OK: PyInstaller"
Write-Host ""

# --- Build backend executable ---
Write-Host "[2/6] Building backend executable..." -ForegroundColor Yellow
$buildBackendScript = Join-Path $PSScriptRoot "build-backend.ps1"
& powershell -ExecutionPolicy Bypass -File $buildBackendScript -ProjectRoot $ProjectRoot
if ($LASTEXITCODE -ne 0) {
    Write-Error "Backend build failed."
    exit 1
}
Write-Host ""

# --- Copy backend to Tauri resources ---
Write-Host "[3/6] Preparing Tauri backend resources..." -ForegroundColor Yellow
$tauriSrcDir = Join-Path (Join-Path $ProjectRoot "tauri-app") "src-tauri"
$backendResourceDir = Join-Path $tauriSrcDir "backend"

if (Test-Path $backendResourceDir) {
    Remove-Item -Recurse -Force $backendResourceDir
}
$distBackend = Join-Path (Join-Path $ProjectRoot "dist") "neuroflow-backend"
Copy-Item -Recurse -Force $distBackend $backendResourceDir
Write-Host "  Copied backend to: $backendResourceDir"
Write-Host ""

# --- Install frontend dependencies ---
Write-Host "[4/6] Installing frontend dependencies..." -ForegroundColor Yellow
$tauriAppDir = Join-Path $ProjectRoot "tauri-app"
Push-Location $tauriAppDir
try {
    if (-not (Test-Path "node_modules")) {
        npm install
        if ($LASTEXITCODE -ne 0) {
            Write-Error "npm install failed."
            exit 1
        }
    } else {
        Write-Host "  node_modules exists, skipping install."
    }
} finally {
    Pop-Location
}
Write-Host ""

# --- Ensure Windows icon exists ---
Write-Host "[5/7] Preparing Windows icon..." -ForegroundColor Yellow
$iconPng = Join-Path (Join-Path $tauriSrcDir "icons") "icon.png"
$iconIco = Join-Path (Join-Path $tauriSrcDir "icons") "icon.ico"
if (-not (Test-Path $iconIco)) {
    if (-not (Test-Path $iconPng)) {
        Write-Error "Missing icon source: $iconPng"
        exit 1
    }
    & $python -c "from PIL import Image; import sys; src, dst = sys.argv[1], sys.argv[2]; img = Image.open(src).convert('RGBA'); img.save(dst, sizes=[(256,256),(128,128),(64,64),(48,48),(32,32),(16,16)])" $iconPng $iconIco
    if ($LASTEXITCODE -ne 0) {
        Write-Error "Failed to generate Windows icon.ico from icon.png."
        exit 1
    }
    Write-Host "  Generated icon.ico"
} else {
    Write-Host "  icon.ico exists"
}
Write-Host ""

# --- Build Tauri app ---
Write-Host "[6/7] Building Tauri app..." -ForegroundColor Yellow
Push-Location $tauriAppDir
try {
    npm run tauri build
    if ($LASTEXITCODE -ne 0) {
        Write-Error "Tauri build failed."
        exit 1
    }
} finally {
    Pop-Location
}
Write-Host ""

# --- Assemble portable folder ---
Write-Host "[7/7] Assembling portable folder..." -ForegroundColor Yellow
$portableDir = Join-Path (Join-Path (Join-Path $ProjectRoot "dist-portable") "windows") "NeuroFlowPortable"

if (Test-Path $portableDir) {
    Stop-PortableProcesses -PortableDir $portableDir
    Remove-Item -Recurse -Force $portableDir
}
New-Item -ItemType Directory -Path $portableDir -Force | Out-Null

# Find Tauri build output
$tauriRelease = Join-Path (Join-Path $tauriSrcDir "target") "release"
$tauriBundle = Join-Path $tauriRelease "bundle"

# Copy the main executable. Cargo uses the binary name from Cargo.toml
# (`mri-pipeline-tauri.exe`), while the portable distribution exposes it as
# `NeuroFlow.exe` for users.
$exeCandidates = @(
    (Join-Path $tauriRelease "NeuroFlow.exe"),
    (Join-Path $tauriRelease "mri-pipeline-tauri.exe")
)
$exePath = $null
foreach ($candidate in $exeCandidates) {
    if (Test-Path $candidate) {
        $exePath = $candidate
        break
    }
}
if (-not $exePath -and (Test-Path $tauriBundle)) {
    $exePath = Get-ChildItem -Path $tauriBundle -Filter "*.exe" -Recurse -ErrorAction SilentlyContinue |
        Where-Object { $_.Name -in @("NeuroFlow.exe", "mri-pipeline-tauri.exe") } |
        Select-Object -First 1 -ExpandProperty FullName
}
if ($exePath -and (Test-Path $exePath)) {
    Copy-Item $exePath (Join-Path $portableDir "NeuroFlow.exe")
    Write-Host "  Copied $([System.IO.Path]::GetFileName($exePath)) as NeuroFlow.exe"
} else {
    Write-Error "Tauri executable not found. Expected NeuroFlow.exe or mri-pipeline-tauri.exe under $tauriRelease."
    exit 1
}

# Copy Tauri runtime files (WebView2 loader, etc.)
$tauriRuntimeFiles = @("WebView2Loader.dll", "neuroflow.pdb")
foreach ($file in $tauriRuntimeFiles) {
    $src = Join-Path $tauriRelease $file
    if (Test-Path $src) {
        Copy-Item $src $portableDir
    }
}

# Copy backend one-dir output
$portableBackend = Join-Path $portableDir "backend"
Copy-Item -Recurse -Force $backendResourceDir $portableBackend
Write-Host "  Copied backend/"

# Create data directories
$dirs = @("config", "outputs", "outputs\jobs", "logs", "licenses")
foreach ($dir in $dirs) {
    New-Item -ItemType Directory -Path (Join-Path $portableDir $dir) -Force | Out-Null
}
Write-Host "  Created data directories"

# Write README
$readmeContent = @"
NeuroFlow Portable for Windows
================================

Quick Start:
  1. Double-click NeuroFlow.exe to launch the application.
  2. The Python backend starts automatically (no system Python needed).
  3. Close the window to stop the backend.

Prerequisites (Host Machine):
  - Windows 10 or Windows 11
  - Docker Desktop installed and running
    Download from: https://www.docker.com/products/docker-desktop/
  - Required Docker images must be pulled on the host.
    Check the Tools Configuration screen in the app for image status.
  - SSH client (included in Windows 10/11 by default)
  - FreeSurfer license file (if using FreeSurfer-based tools)
    Place your license.txt in the licenses/ folder.

Portable Data:
  - App configs are stored in: config/
  - Job registry and logs are stored in: outputs/jobs/
  - Uploaded licenses are stored in: licenses/

Moving/Copying:
  - Copy the entire NeuroFlowPortable folder to any location.
  - All data stays inside the folder.

Known Limitations:
  - Docker Desktop must be installed separately on the host.
  - GPU acceleration is not configured automatically.
  - macOS and Linux builds are not included.
  - Large Docker images may need to be pulled on first use.

"@
$readmePath = Join-Path $portableDir "README-PORTABLE.txt"
Set-Content -Path $readmePath -Value $readmeContent -Encoding UTF8
Write-Host "  Wrote README-PORTABLE.txt"

# Create shortcuts (optional)
try {
    $shell = New-Object -ComObject WScript.Shell
    $shortcutPath = Join-Path $portableDir "NeuroFlow.lnk"
    $shortcut = $shell.CreateShortcut($shortcutPath)
    $shortcut.TargetPath = Join-Path $portableDir "NeuroFlow.exe"
    $shortcut.WorkingDirectory = $portableDir
    $shortcut.Description = "Launch NeuroFlow"
    $shortcut.Save()
    Write-Host "  Created NeuroFlow.lnk"

    $debugShortcutPath = Join-Path $portableDir "NeuroFlow Debug.lnk"
    $debugShortcut = $shell.CreateShortcut($debugShortcutPath)
    $debugShortcut.TargetPath = "cmd.exe"
    $debugShortcut.Arguments = "/k `"cd /d `"$portableDir`" && NeuroFlow.exe`""
    $debugShortcut.WorkingDirectory = $portableDir
    $debugShortcut.Description = "Launch NeuroFlow with debug console"
    $debugShortcut.Save()
    Write-Host "  Created NeuroFlow Debug.lnk"
} catch {
    Write-Host "  Skipped shortcut creation (COM automation not available)"
}

Write-Host ""
Write-Host "========================================" -ForegroundColor Green
Write-Host "  Build Complete!" -ForegroundColor Green
Write-Host "========================================" -ForegroundColor Green
Write-Host ""
Write-Host "Portable folder: $portableDir"
Write-Host ""
Write-Host "To test:" -ForegroundColor Cyan
Write-Host "  1. Copy NeuroFlowPortable to a different location"
Write-Host "  2. Double-click NeuroFlow.exe"
Write-Host "  3. Verify the health check succeeds"
Write-Host ""
