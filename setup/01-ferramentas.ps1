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

Passo "OBS, DroidCam e ffmpeg"
# DroidCam Client -> traz o driver de camera virtual, que e o unico caminho
#                    para o emulador enxergar o que o OBS produz.
# DroidCam OBS Plugin -> adiciona Ferramentas > DroidCam Virtual Output no OBS.
# Sem esses dois, o modo "camera ao vivo" e "video sobreposto" nao funcionam.
$programas = @(
    @{ id = "OBSProject.OBSStudio";          nome = "OBS Studio" },
    @{ id = "dev47apps.DroidCam";            nome = "DroidCam Client (driver)" },
    @{ id = "dev47apps.DroidCamOBSPlugin";   nome = "DroidCam OBS Plugin" },
    @{ id = "Gyan.FFmpeg";                   nome = "ffmpeg" }
)
foreach ($prog in $programas) {
    Write-Host "  instalando $($prog.nome)"
    winget install --id $($prog.id) -e --accept-package-agreements --accept-source-agreements --silent
}

Write-Host @"

  FALTA UM, e nao esta no winget:

    Iriun Webcam  ->  https://iriun.com/
    (baixe o cliente de Windows e o app no celular)

  Ele so e necessario para usar a CAMERA DO CELULAR ao vivo.
  Para rodar video na camera voce nao precisa dele nem do OBS:
      emulator -avd MinutePlay -camera-back "videofile:C:\seuideo.mp4" ...

  Depois de instalar o OBS, ligue o servidor websocket uma vez:
      OBS > Ferramentas > Configuracoes do WebSocket > ativar servidor
  O camvideo.py le a senha sozinho de
      %APPDATA%\obs-studio\plugin_config\obs-websocket\config.json
"@ -ForegroundColor Yellow

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
