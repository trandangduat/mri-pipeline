# Script khoi chay toan bo NeuroFlow (Backend + Desktop GUI)
Write-Host "Dang khoi chay NeuroFlow..." -ForegroundColor Cyan
Set-Location -Path "$PSScriptRoot\tauri-app"
npm run tauri dev
