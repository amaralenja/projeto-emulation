# 02 - Cria o AVD "MinutePlay" com a configuracao que funciona.
#
#   powershell -ExecutionPolicy Bypass -File .\02-criar-avd.ps1

$ErrorActionPreference = "Stop"
$SDK = "$env:LOCALAPPDATA\Android\Sdk"
$env:ANDROID_SDK_ROOT = $SDK
$env:ANDROID_HOME = $SDK
$AVD = "MinutePlay"
$avdPath = "$env:USERPROFILE\.android\avd\$AVD.avd"

if (Test-Path $avdPath) {
    Write-Host "AVD '$AVD' ja existe em $avdPath" -ForegroundColor Yellow
    $r = Read-Host "Apagar e recriar? (s/N)"
    if ($r -ne "s") { exit }
    Remove-Item -Recurse -Force $avdPath
    Remove-Item -Force "$env:USERPROFILE\.android\avd\$AVD.ini" -ErrorAction SilentlyContinue
}

Write-Host "`n=== Criando o AVD ===" -ForegroundColor Cyan
# A imagem TEM que ser google_apis_playstore: o Minute e protegido por PAIRIP e
# so passa se for instalado pela Play Store com conta logada. Imagem sem Play
# trava no "Something went wrong / Check that Google Play is enabled".
$avdmanager = "$SDK\cmdline-tools\latest\bin\avdmanager.bat"
"no" | & $avdmanager create avd -n $AVD `
    -k "system-images;android-33;google_apis_playstore;x86_64" -d pixel_5

Write-Host "`n=== Ajustando config.ini ===" -ForegroundColor Cyan
$cfg = "$avdPath\config.ini"
$ajustes = @{
    "hw.camera.back"  = "emulated"     # sintetica: unica fonte que aceita a ultra-wide
    "hw.camera.front" = "webcam0"      # webcam do PC (DroidCam/OBS), se houver
    "hw.keyboard"     = "yes"
    "hw.ramSize"      = "4096"
    "hw.gpu.enabled"  = "yes"
    "hw.gpu.mode"     = "auto"
    "PlayStore.enabled" = "yes"
    "disk.dataPartition.size" = "8G"
}
$linhas = Get-Content $cfg
foreach ($k in $ajustes.Keys) {
    $v = $ajustes[$k]
    if ($linhas -match "^$([regex]::Escape($k))\s*=") {
        $linhas = $linhas -replace "^$([regex]::Escape($k))\s*=.*", "$k = $v"
    } else {
        $linhas += "$k = $v"
    }
}
$linhas | Set-Content $cfg -Encoding UTF8

Write-Host "`nAVD criado." -ForegroundColor Green
Write-Host @"

PROXIMOS PASSOS (manuais, precisam de voce):

  1. Suba o emulador:
       emulator -avd $AVD -no-snapshot -timezone America/Sao_Paulo -gpu auto

  2. Abra a Play Store dentro dele e faca login na sua conta Google.

  3. Instale o Minute PELA PLAY STORE (procure "Minute Data").
     Nao use adb install com os APKs de /apk - eles sao so backup.
     Sideload NAO passa no PAIRIP.

  4. Faca login no Minute.

  5. Rode 03-rootear.sh (no Git Bash) para instalar o Magisk.
"@
