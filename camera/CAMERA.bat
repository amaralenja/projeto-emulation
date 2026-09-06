@echo off
setlocal enabledelayedexpansion
title CAMERA - fonte da camera do emulador
color 0B

set "SDK=%LOCALAPPDATA%\Android\Sdk"
set "ANDROID_SDK_ROOT=%SDK%"
set "ANDROID_HOME=%SDK%"
set "EMU=%SDK%\emulator\emulator.exe"
set "ADB=%SDK%\platform-tools\adb.exe"
set "AVD=MinutePlay"
rem caminho relativo ao .bat: a pasta pode ir pra qualquer lugar
for %%I in ("%~dp0..") do set "RAIZ=%%~fI"
set "BASE=%RAIZ%\camvideo"
set "PREPARAR=%BASE%\preparar.py"
set "VIDEOS=%BASE%\videos"

if not exist "%VIDEOS%" mkdir "%VIDEOS%"

rem --- achar o python de verdade -------------------------------------------
rem "python" no PATH de um Windows limpo e o stub de 0 byte da Microsoft Store:
rem ele abre a loja e nao roda nada. Preferir o interpretador instalado.
set "PY="
for %%P in ("%LOCALAPPDATA%\Programs\Python\Python312\python.exe"
            "%LOCALAPPDATA%\Programs\Python\Python311\python.exe"
            "%ProgramFiles%\Python312\python.exe") do (
    if not defined PY if exist %%P set "PY=%%~P"
)
if not defined PY (
    py -3 --version >nul 2>&1 && set "PY=py -3"
)
if not defined PY (
    echo.
    echo Nao achei o Python. Rode setup\01-ferramentas.ps1 primeiro.
    echo.
    pause
    exit /b 1
)

:menu
cls
echo ===========================================================
echo    CAMERA DO EMULADOR
echo ===========================================================
echo.
echo   [1] VIDEO         um video seu entra como camera traseira
echo   [2] SINTETICA     cena 3D do emulador  ^(o Minute exige esta^)
echo.
echo   [3] Abrir a pasta de videos
echo   [0] Sair
echo.
echo   Pasta de videos: %VIDEOS%
echo.
echo   Camera do celular ao vivo e video sobreposto sairam do menu:
echo   dependiam da saida virtual do DroidCam, que nao existe mais
echo   nas versoes atuais do plugin. Ver a secao 4 do README.
echo.
set "op="
set /p "op=Opcao: "

if "%op%"=="1" goto video
if "%op%"=="2" goto sintetica
if "%op%"=="3" start "" "%VIDEOS%" & goto menu
if "%op%"=="0" exit /b
goto menu

rem ---------------------------------------------------- escolher um video
:escolher
set "ESCOLHIDO="
set /a n=0
cls
echo --- VIDEOS DISPONIVEIS ---
echo.
rem os *.pronto.* sao gerados por este painel; nao entram na lista
for %%f in ("%VIDEOS%\*.mp4" "%VIDEOS%\*.mov" "%VIDEOS%\*.mkv" "%VIDEOS%\*.webm" "%VIDEOS%\*.avi") do (
    echo %%~nf| findstr /i /e ".pronto" >nul || (
        set /a n+=1
        set "arq!n!=%%~ff"
        echo    !n!^) %%~nxf
    )
)
if %n%==0 (
    echo    (vazia^)
    echo.
    echo Jogue seus videos em: %VIDEOS%
    echo.
    pause
    exit /b 1
)
echo.
echo    A^) arrastar um arquivo de outro lugar
echo    V^) voltar
echo.
set "esc="
set /p "esc=Numero do video: "

if /i "%esc%"=="V" exit /b 1
if /i "%esc%"=="A" (
    set "manual="
    set /p "manual=Arraste o arquivo aqui e de Enter: "
    set manual=!manual:"=!
    if "!manual!"=="" exit /b 1
    set "ESCOLHIDO=!manual!"
    exit /b 0
)
set "ESCOLHIDO=!arq%esc%!"
if "!ESCOLHIDO!"=="" (
    echo Opcao invalida.
    ping -n 3 127.0.0.1 >nul
    goto escolher
)
exit /b 0

rem ---------------------------------------------------------------- modos
:video
call :escolher
if errorlevel 1 goto menu

rem preparar.py grava <base>.pronto<ext> ao lado da entrada
for %%I in ("!ESCOLHIDO!") do set "PRONTO=%%~dpnI.pronto%%~xI"

set "REFAZER=S"
if exist "!PRONTO!" (
    echo.
    echo Ja existe preparado:
    echo    !PRONTO!
    set "REFAZER="
    set /p "REFAZER=Preparar de novo? (s/N): "
)
if /i "!REFAZER!"=="S" (
    echo.
    echo Preparando ^(gira e encaixa em 1280x720^)...
    echo Sem isso a imagem chega cortada: o buffer da camera e 1280x720
    echo deitado, e um vertical perde cerca de 68%% da altura.
    echo.
    %PY% "%PREPARAR%" "!ESCOLHIDO!" "!PRONTO!"
    if errorlevel 1 (
        echo.
        echo Falhou ao preparar o video.
        pause
        goto menu
    )
)
if not exist "!PRONTO!" (
    echo Arquivo preparado nao encontrado: !PRONTO!
    pause
    goto menu
)

rem ARMADILHA: o `videofile:` do emulador NAO aceita espaco no caminho, e falha
rem calado -- o emulador sobe, o CameraService abre o dispositivo, e nao chega
rem frame nenhum; o app fica travado esperando. Nao adianta por entre aspas:
rem testado com o mesmo arquivo nos dois caminhos, so o sem espaco entrega.
rem A pasta deste projeto se chama "PROJETO EMULATION", entao sempre cai nisso.
rem Por isso copiamos para uma area sem espaco antes de subir.
set "AREA=%LOCALAPPDATA%\emulation-cam"
if not exist "%AREA%" mkdir "%AREA%"
set "CAMFILE=%AREA%\atual.mp4"
echo.
echo Copiando para area sem espaco no caminho...
copy /y "!PRONTO!" "!CAMFILE!" >nul
if errorlevel 1 (
    echo Falhou ao copiar para !CAMFILE!
    pause
    goto menu
)
set "CAM=videofile:!CAMFILE!"
goto subir

:sintetica
set "CAM=emulated"
goto subir

rem ---------------------------------------------------------------- subir
:subir
echo.
echo Encerrando emulador anterior e limpando locks...
"%ADB%" -s emulator-5554 emu kill >nul 2>&1
ping -n 7 127.0.0.1 >nul
del /q "%USERPROFILE%\.android\avd\%AVD%.avd\*.lock" >nul 2>&1
rmdir /s /q "%USERPROFILE%\.android\avd\%AVD%.avd\hardware-qemu.ini.lock" >nul 2>&1
rmdir /s /q "%USERPROFILE%\.android\avd\%AVD%.avd\multiinstance.lock" >nul 2>&1

echo Subindo o emulador (traseira = !CAM!)...
"%EMU%" -avd %AVD% -no-snapshot -timezone America/Sao_Paulo -camera-back "!CAM!" -camera-front emulated -gpu auto
goto menu
