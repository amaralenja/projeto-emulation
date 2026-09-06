# 01 - Instala as ferramentas base e o SDK do Android.
# Rode no PowerShell. Nao precisa ser administrador (o winget instala no usuario).
#
#   powershell -ExecutionPolicy Bypass -File .\01-ferramentas.ps1

$ErrorActionPreference = "Stop"
$SDK = "$env:LOCALAPPDATA\Android\Sdk"

function Passo($t) { Write-Host "`n=== $t ===" -ForegroundColor Cyan }

# O winget escreve o PATH novo no registro, mas o processo atual continua com o
# PATH antigo. Sem recarregar, nada que foi instalado agora e visivel aqui.
function Recarregar-Path {
    $maquina = [Environment]::GetEnvironmentVariable("Path", "Machine")
    $usuario = [Environment]::GetEnvironmentVariable("Path", "User")
    $env:Path = @($maquina, $usuario | Where-Object { $_ }) -join ";"
}

# ARMADILHA: num Windows limpo, "python" no PATH e o atalho da Microsoft Store
# (%LOCALAPPDATA%\Microsoft\WindowsApps\python.exe, um stub de 0 byte que abre a
# loja). Chamar "python -m pip" logo depois do winget cai nele, e como falha de
# .exe nativo NAO dispara o $ErrorActionPreference, o script seguia adiante sem
# instalar o websockets -- e o camvideo.py so quebrava muito depois com
# ModuleNotFoundError. Por isso achamos o interpretador de verdade pelo caminho.
function Achar-Python {
    Recarregar-Path
    $candidatos = @("$env:LOCALAPPDATA\Programs\Python\Python312\python.exe")
    foreach ($raiz in "$env:LOCALAPPDATA\Programs\Python", "$env:ProgramFiles") {
        $candidatos += Get-ChildItem "$raiz\Python3*\python.exe" -ErrorAction SilentlyContinue |
                       Sort-Object FullName -Descending | ForEach-Object { $_.FullName }
    }
    $candidatos += Get-Command python.exe -All -ErrorAction SilentlyContinue |
                   ForEach-Object { $_.Source }

    foreach ($c in $candidatos) {
        if (-not $c) { continue }
        if ($c -like "*\WindowsApps\*") { continue }          # stub da Store
        if (-not (Test-Path $c)) { continue }
        if ((Get-Item $c).Length -eq 0) { continue }          # stub tem 0 byte
        return $c
    }
    return $null
}

# ARMADILHA IRMA DA DE CIMA, e pior: o winget instala o Temurin com --silent, e
# nesse modo o MSI NAO poe o java no PATH nem cria o JAVA_HOME (sao features
# opcionais, desligadas por padrao). O sdkmanager.bat morre no ato com
# "JAVA_HOME is not set", mas a saida ia toda para Out-Null e falha de .bat nao
# dispara o $ErrorActionPreference -- entao o script imprimia "instalando X"
# para os cinco pacotes, nao instalava nenhum, e terminava anunciando sucesso.
# O javac e o keytool do lentes/build.sh dependem do mesmo PATH.
function Achar-Java {
    if ($env:JAVA_HOME -and (Test-Path "$env:JAVA_HOME\bin\java.exe")) {
        return $env:JAVA_HOME
    }
    $raizes = @(
        "$env:ProgramFiles\Eclipse Adoptium",
        "${env:ProgramFiles(x86)}\Eclipse Adoptium",
        "$env:LOCALAPPDATA\Programs\Eclipse Adoptium",
        "$env:ProgramFiles\Java"
    )
    foreach ($r in $raizes) {
        $achado = Get-ChildItem "$r\jdk*" -Directory -ErrorAction SilentlyContinue |
                  Where-Object { Test-Path "$($_.FullName)\bin\java.exe" } |
                  Sort-Object Name -Descending | Select-Object -First 1
        if ($achado) { return $achado.FullName }
    }
    $cmd = Get-Command java.exe -ErrorAction SilentlyContinue
    if ($cmd) { return (Split-Path (Split-Path $cmd.Source -Parent) -Parent) }
    return $null
}

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
$jdk = Achar-Java
if (-not $jdk) {
    Write-Host @"

  Nao achei um JDK. O sdkmanager nao roda sem Java.

  Confira se o Temurin 21 entrou:
      winget list --id EclipseAdoptium.Temurin.21.JDK
  e onde ele foi parar (normalmente C:\Program Files\Eclipse Adoptium\jdk-21...).
  Depois rode este script de novo.
"@ -ForegroundColor Red
    exit 1
}
$env:JAVA_HOME = $jdk
$env:Path = "$jdk\bin;$env:Path"
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
    "system-images;android-33;google_apis_playstore;x86_64"
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

Write-Host "`nPronto. SDK em $SDK" -ForegroundColor Green
Write-Host "Abra um PowerShell NOVO (pro PATH valer) e rode 02-criar-avd.ps1"
