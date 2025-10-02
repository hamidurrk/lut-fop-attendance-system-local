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

$pyinstallerArgs = @(
    '--clean',
    '--noconfirm',
    '--specpath', (Join-Path $projectRoot 'build_scripts'),
    (Join-Path $projectRoot 'build_scripts' 'attendance_app.spec')
)

if ($Mode -eq 'onefile') {
    $pyinstallerArgs += '--onefile'
}

& $pythonExe -m PyInstaller @pyinstallerArgs
