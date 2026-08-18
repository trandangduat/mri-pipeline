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
