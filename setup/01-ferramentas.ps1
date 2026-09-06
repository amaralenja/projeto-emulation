# 01 - Instala as ferramentas base e o SDK do Android.
# Rode no PowerShell. Nao precisa ser administrador (o winget instala no usuario).
#
#   powershell -ExecutionPolicy Bypass -File .\01-ferramentas.ps1

$ErrorActionPreference = "Stop"
$SDK = "$env:LOCALAPPDATA\Android\Sdk"

function Passo($t) { Write-Host "`n=== $t ===" -ForegroundColor Cyan }

Passo "Ferramentas base (JDK, Python, 7zip)"
# JDK: o sdkmanager e o javac precisam dele. Python: roda o camvideo.py.
winget install --id EclipseAdoptium.Temurin.21.JDK -e --accept-source-agreements --accept-package-agreements --silent
winget install --id Python.Python.3.12 -e --accept-package-agreements --silent

Passo "Bibliotecas Python"
# websockets: e por onde o camvideo.py fala com o OBS.
python -m pip install --upgrade pip
python -m pip install websockets

Passo "Ferramentas de linha de comando do Android"
$cmdlineZip = "$env:TEMP\cmdline-tools.zip"
$destino = "$SDK\cmdline-tools"
if (-not (Test-Path "$destino\latest\bin\sdkmanager.bat")) {
    New-Item -ItemType Directory -Force -Path $destino | Out-Null
    Invoke-WebRequest -Uri "https://dl.google.com/android/repository/commandlinetools-win-11076708_latest.zip" -OutFile $cmdlineZip
    Expand-Archive -Path $cmdlineZip -DestinationPath $destino -Force
    # o zip extrai como "cmdline-tools"; o sdkmanager exige que esteja em "latest"
    if (Test-Path "$destino\cmdline-tools") {
        Move-Item "$destino\cmdline-tools" "$destino\latest" -Force
    }
    Remove-Item $cmdlineZip -Force
} else {
    Write-Host "ja instalado, pulando"
}

Passo "Componentes do SDK (demora, sao alguns GB)"
$sdkmanager = "$SDK\cmdline-tools\latest\bin\sdkmanager.bat"
$env:ANDROID_SDK_ROOT = $SDK
$env:ANDROID_HOME = $SDK

# build-tools 37: as versoes antigas (34) quebram com class files de JDK novo,
# o d8 estoura NullPointerException ao ler classe anonima.
# As licencas travam a instalacao se nao forem aceitas antes.
Write-Host "  aceitando licencas"
$licencas = "y`n" * 30
$licencas | & $sdkmanager --sdk_root="$SDK" --licenses | Out-Null

$pacotes = @(
    "platform-tools",
    "emulator",
    "platforms;android-34",
    "build-tools;37.0.0",
    "system-images;android-33;google_apis_playstore;x86_64"
)
foreach ($p in $pacotes) {
    Write-Host "  instalando $p"
    "y" | & $sdkmanager --sdk_root="$SDK" $p | Out-Null
}

Passo "Opcionais: OBS e ffmpeg"
# So precisa se voce for usar camera do celular ao vivo, ou vídeo sobreposto.
# Para vídeo simples o emulador toca o arquivo sozinho (-camera-back videofile:...)
$r = Read-Host "Instalar OBS Studio e ffmpeg? (s/N)"
if ($r -eq "s") {
    winget install --id OBSProject.OBSStudio -e --accept-package-agreements --silent
    winget install --id Gyan.FFmpeg -e --accept-package-agreements --silent
    Write-Host @"

  Faltam dois programas que NAO estao no winget, baixe manualmente:
    DroidCam Client (inclui o driver + plugin do OBS)  https://www.dev47apps.com/
    Iriun Webcam (camera do celular)                   https://iriun.com/

  E no OBS: Ferramentas > Configuracoes do WebSocket > ligar o servidor.
  O camvideo.py le a senha sozinho de:
    %APPDATA%\obs-studio\plugin_config\obs-websocket\config.json
"@ -ForegroundColor Yellow
}

Passo "PATH"
$novos = "$SDK\platform-tools", "$SDK\emulator"
$atual = [Environment]::GetEnvironmentVariable("Path", "User")
foreach ($n in $novos) {
    if ($atual -notlike "*$n*") {
        $atual = "$atual;$n"
    }
}
[Environment]::SetEnvironmentVariable("Path", $atual, "User")
[Environment]::SetEnvironmentVariable("ANDROID_SDK_ROOT", $SDK, "User")
[Environment]::SetEnvironmentVariable("ANDROID_HOME", $SDK, "User")

Write-Host "`nPronto. SDK em $SDK" -ForegroundColor Green
Write-Host "Abra um PowerShell NOVO (pro PATH valer) e rode 02-criar-avd.ps1"
