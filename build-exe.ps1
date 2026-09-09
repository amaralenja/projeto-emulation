param(
    [switch] $NaoInstalarDependencias
)

$ErrorActionPreference = 'Stop'
$raiz = Split-Path -Parent $MyInvocation.MyCommand.Path
$entrada = Join-Path $raiz 'camvideo\modern_server.pyw'
$dist = Join-Path $raiz 'dist'
$work = Join-Path $raiz 'build\pyinstaller'

if (-not $NaoInstalarDependencias) {
    python -m pip install --disable-pip-version-check --quiet 'pyinstaller>=6.0,<7.0'
    if ($LASTEXITCODE -ne 0) { throw 'Nao foi possivel instalar o PyInstaller.' }
}

python -m PyInstaller `
    --noconfirm `
    --clean `
    --onefile `
    --windowed `
    --name CameraEmulador `
    --distpath $dist `
    --workpath $work `
    --specpath (Join-Path $work 'spec') `
    --add-data "$(Join-Path $raiz 'camvideo\montar.py');." `
    --add-data "$(Join-Path $raiz 'camvideo\instalar-videocam.ps1');." `
    --add-data "$(Join-Path $raiz 'camvideo\controlar-videocam.ps1');." `
    --add-data "$(Join-Path $raiz 'camvideo\painel.pyw');." `
    --add-data "$(Join-Path $raiz 'camvideo\web');web" `
    --hidden-import montar `
    $entrada

if ($LASTEXITCODE -ne 0) { throw 'A criacao do executavel falhou.' }

$videos = Join-Path $dist 'videos'
New-Item -ItemType Directory -Path $videos -Force | Out-Null
Write-Host "Executavel pronto: $(Join-Path $dist 'CameraEmulador.exe')"
