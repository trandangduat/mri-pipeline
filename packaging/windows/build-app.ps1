param(
    [string]$ProjectRoot = (Split-Path $PSScriptRoot | Split-Path)
)

$ErrorActionPreference = "Stop"

# The public Windows distribution is the native NSIS installer.  Keep the
# portable-folder builder available only as an explicit local workflow.
& (Join-Path $PSScriptRoot "build-portable.ps1") -ProjectRoot $ProjectRoot -SkipPortable
exit $LASTEXITCODE
