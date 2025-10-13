param(
    [ValidateSet('onedir', 'onefile')]
    [string]$Mode = 'onedir'
)

$ErrorActionPreference = 'Stop'

$projectRoot = Split-Path -Parent $PSScriptRoot
$venvPath = Join-Path $projectRoot '.venv'
$pythonExe = Join-Path (Join-Path $venvPath 'Scripts') 'python.exe'

if (-not (Test-Path $venvPath)) {
    python -m venv $venvPath
}

& $pythonExe -m pip install --upgrade pip
& $pythonExe -m pip install -r (Join-Path $projectRoot 'requirements.txt')

$specDir = Join-Path $projectRoot 'build_scripts'
$specFile = Join-Path $specDir 'attendance_app.spec'

if (-not (Test-Path $specFile)) {
    throw "Spec file not found at $specFile"
}

$pyinstallerArgs = @(
    '--clean',
    '--noconfirm',
    $specFile
)

$previousMode = $env:PYINSTALLER_BUILD_MODE
try {
    $env:PYINSTALLER_BUILD_MODE = $Mode
    $env:PYINSTALLER_SPEC_PATH = $specFile
    & $pythonExe -m PyInstaller @pyinstallerArgs
}
finally {
    if ($null -eq $previousMode) {
        Remove-Item Env:PYINSTALLER_BUILD_MODE -ErrorAction Ignore
    } else {
        $env:PYINSTALLER_BUILD_MODE = $previousMode
    }
    Remove-Item Env:PYINSTALLER_SPEC_PATH -ErrorAction Ignore
}
