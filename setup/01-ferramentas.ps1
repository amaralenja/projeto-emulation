# 01 - Instala as ferramentas base e o SDK do Android.
# Rode no PowerShell. Nao precisa ser administrador (o winget instala no usuario).
#
#   powershell -ExecutionPolicy Bypass -File .\01-ferramentas.ps1

$ErrorActionPreference = "Stop"
$SDK = "$env:LOCALAPPDATA\Android\Sdk"

. "$PSScriptRoot\comum.ps1"

function Passo($t) { Write-Host "`n=== $t ===" -ForegroundColor Cyan }

Passo "Ferramentas base (JDK e Python)"
# JDK: o sdkmanager e o javac precisam dele. Python: roda o camvideo.py.
winget install --id EclipseAdoptium.Temurin.21.JDK -e --accept-source-agreements --accept-package-agreements --silent
winget install --id Python.Python.3.12 -e --accept-package-agreements --silent

Passo "Bibliotecas Python"
# websockets: e por onde o camvideo.py fala com o OBS.
$py = Achar-Python
if (-not $py) {
    Write-Host @"

  Nao achei um python.exe utilizavel.

  O winget pode ter pedido reinicio, ou o unico "python" do PATH e o atalho da
  Microsoft Store. Abra um PowerShell NOVO, confira com

      (Get-Command python).Source

  e, se apontar para ...\WindowsApps\, desligue o alias em
  Configuracoes > Aplicativos > Configuracoes avancadas > Aliases de execucao.
  Depois rode este script de novo.
"@ -ForegroundColor Red
    exit 1
}
Write-Host "  usando $py"
& $py -m pip install --upgrade pip
& $py -m pip install websockets
if ($LASTEXITCODE -ne 0) {
    Write-Host "  ERRO: nao deu para instalar o websockets. O camvideo.py nao vai rodar." -ForegroundColor Red
    exit 1
}

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

# sem isso o sdkmanager.bat nao acha o java e o passo inteiro falha calado
$jdk = Preparar-Java
Write-Host "  JAVA_HOME = $jdk"

# build-tools 37: as versoes antigas (34) quebram com class files de JDK novo,
# o d8 estoura NullPointerException ao ler classe anonima.
# As licencas travam a instalacao se nao forem aceitas antes.
#
# ARMADILHA: `$texto | & $sdkmanager` NAO funciona. O sdkmanager.bat e um
# wrapper que chama java, e o pipe do PowerShell nao entrega o stdin ate la: o
# prompt "Review licenses that have not been accepted (y/N)?" le EOF e recusa
# tudo. O sintoma e "7 of 7 SDK package licenses not accepted", seguido de
# "Skipping following packages as the license is not accepted" em cada pacote
# -- e o sdkmanager SAI 0 assim mesmo. Redirecionar um arquivo pelo cmd entrega.
Write-Host "  aceitando licencas"
$sim = Join-Path $env:TEMP "sdk-yes.txt"
(1..100 | ForEach-Object { "y" }) -join "`r`n" | Set-Content $sim -Encoding ASCII
cmd /c "`"$sdkmanager`" --sdk_root=`"$SDK`" --licenses < `"$sim`""
if (-not (Test-Path "$SDK\licenses\android-sdk-license")) {
    Write-Host "  ERRO: as licencas do SDK nao foram aceitas." -ForegroundColor Red
    exit 1
}

$pacotes = @(
    "platform-tools",
    "emulator",
    "platforms;android-34",
    "build-tools;37.0.0",
    "system-images;android-33;google_apis_playstore;x86_64",
    # driver de aceleracao: sem hipervisor o emulador x86_64 nao sobe, morre com
    # "x86_64 emulation currently requires hardware acceleration!". Baixar da
    # para fazer aqui; INSTALAR precisa de admin -- ver o aviso no fim do script.
    "extras;google;Android_Emulator_Hypervisor_Driver"
)
foreach ($p in $pacotes) {
    Write-Host "  instalando $p"
    cmd /c "`"$sdkmanager`" --sdk_root=`"$SDK`" `"$p`" < `"$sim`""
    if ($LASTEXITCODE -ne 0) {
        Write-Host "  ERRO: falhou ao instalar '$p' (codigo $LASTEXITCODE)." -ForegroundColor Red
        exit 1
    }
}

# confere no disco: sdkmanager ja saiu 0 sem ter baixado nada
Write-Host "  conferindo o que chegou no disco"
$esperado = @{
    "platform-tools"                                    = "platform-tools\adb.exe"
    "emulator"                                          = "emulator\emulator.exe"
    "platforms;android-34"                              = "platforms\android-34\android.jar"
    "build-tools;37.0.0"                                = "build-tools\37.0.0\d8.bat"
    "system-images;android-33;google_apis_playstore;x86_64" = "system-images\android-33\google_apis_playstore\x86_64\system.img"
    "extras;google;Android_Emulator_Hypervisor_Driver"  = "extras\google\Android_Emulator_Hypervisor_Driver\silent_install.bat"
}
$faltando = @()
foreach ($p in $esperado.Keys) {
    if (Test-Path "$SDK\$($esperado[$p])") {
        Write-Host "    ok  $p"
    } else {
        Write-Host "    FALTANDO  $p" -ForegroundColor Red
        $faltando += $p
    }
}
if ($faltando) {
    Write-Host "`n  ERRO: $($faltando.Count) pacote(s) do SDK nao chegaram no disco." -ForegroundColor Red
    exit 1
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
      emulator -avd MinutePlay -camera-back "videofile:C:\caminho\seu\video.mp4" ...

  Depois de instalar o OBS, ligue o servidor websocket uma vez:
      OBS > Ferramentas > Configuracoes do WebSocket > ativar servidor
  O camvideo.py le a senha sozinho de
      %APPDATA%\obs-studio\plugin_config\obs-websocket\config.json
"@ -ForegroundColor Yellow

Passo "PATH"
# o bin do JDK entra junto: o lentes/build.sh chama javac e keytool pelo PATH,
# e o winget --silent nao os coloca la.
$novos = "$SDK\platform-tools", "$SDK\emulator", "$jdk\bin"
$atual = [Environment]::GetEnvironmentVariable("Path", "User")
foreach ($n in $novos) {
    if ($atual -notlike "*$n*") {
        $atual = "$atual;$n"
    }
}
[Environment]::SetEnvironmentVariable("Path", $atual, "User")
[Environment]::SetEnvironmentVariable("ANDROID_SDK_ROOT", $SDK, "User")
[Environment]::SetEnvironmentVariable("ANDROID_HOME", $SDK, "User")
[Environment]::SetEnvironmentVariable("JAVA_HOME", $jdk, "User")

Passo "Aceleracao por hardware"
# O emulador x86_64 nao sobe sem hipervisor -- morre com "x86_64 emulation
# currently requires hardware acceleration!". Instalar o driver exige admin,
# entao este script so diagnostica e diz o que fazer.
$acel = & "$SDK\emulator\emulator.exe" -accel-check 2>&1 | Out-String
if ($acel -match "is installed and usable|HAXM version|WHPX .*installed") {
    Write-Host "  ok, aceleracao disponivel" -ForegroundColor Green
} else {
    $vt = (Get-CimInstance Win32_Processor | Select-Object -First 1).VirtualizationFirmwareEnabled
    Write-Host "  SEM aceleracao. O emulador nao vai subir." -ForegroundColor Yellow
    Write-Host "  VirtualizationFirmwareEnabled = $vt"
    if (-not $vt) {
        Write-Host @"

  A virtualizacao esta DESLIGADA no firmware. Entre no BIOS/UEFI e ligue
  VT-x (Intel) ou SVM/AMD-V (AMD). Sem isso nao ha o que fazer no Windows.
"@ -ForegroundColor Yellow
    } else {
        Write-Host @"

  A CPU suporta; falta so o driver. Abra um PowerShell COMO ADMINISTRADOR e:

      cd "$SDK\extras\google\Android_Emulator_Hypervisor_Driver"
      .\silent_install.bat

  (o pacote ja foi baixado acima). Confira depois com:
      emulator -accel-check
"@ -ForegroundColor Yellow
    }
}

Write-Host "`nPronto. SDK em $SDK" -ForegroundColor Green
Write-Host "Abra um PowerShell NOVO (pro PATH valer) e rode 02-criar-avd.ps1"
