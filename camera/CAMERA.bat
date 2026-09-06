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
set "CAMVIDEO=%BASE%\camvideo.py"
set "VIDEOS=%BASE%\videos"

if not exist "%VIDEOS%" mkdir "%VIDEOS%"

:menu
cls
echo ===========================================================
echo    CAMERA DO EMULADOR
echo ===========================================================
echo.
echo   [1] VIDEO             um video seu, tela cheia
echo   [2] CELULAR AO VIVO   sua camera pelo Iriun
echo   [3] CELULAR + VIDEO   camera ao vivo com video por cima
echo   [4] SINTETICA         cena 3D do emulador (ultra-wide do Minute)
echo.
echo   [5] Abrir a pasta de videos
echo   [6] Listar webcams
echo   [0] Sair
echo.
echo   Pasta de videos: %VIDEOS%
echo.
set "op="
set /p "op=Opcao: "

if "%op%"=="1" goto so_video
if "%op%"=="2" goto so_live
if "%op%"=="3" goto live_video
if "%op%"=="4" goto sintetica
if "%op%"=="5" start "" "%VIDEOS%" & goto menu
if "%op%"=="6" goto listar
if "%op%"=="0" exit /b
goto menu

:listar
cls
python "%CAMVIDEO%" --listar-cams
echo.
pause
goto menu

rem ---------------------------------------------------- escolher um video
:escolher
set "ESCOLHIDO="
set /a n=0
cls
echo --- VIDEOS DISPONIVEIS ---
echo.
for %%f in ("%VIDEOS%\*.mp4" "%VIDEOS%\*.mov" "%VIDEOS%\*.mkv" "%VIDEOS%\*.webm" "%VIDEOS%\*.avi") do (
    set /a n+=1
    set "arq!n!=%%~ff"
    echo    !n!^) %%~nxf
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
    timeout /t 2 /nobreak >nul
    goto escolher
)
exit /b 0

rem ---------------------------------------------------------------- modos
:so_video
call :escolher
if errorlevel 1 goto menu
echo.
python "%CAMVIDEO%" "%ESCOLHIDO%" --rot 270 --flip
if errorlevel 1 ( pause & goto menu )
set "CAM=webcam0"
goto subir

:so_live
cls
echo --- CELULAR AO VIVO ---
echo.
echo Abra o app Iriun no celular e o Iriun Webcam no PC.
echo A imagem tem que aparecer na janela do PC antes de continuar.
echo.
pause
python "%CAMVIDEO%" --live
if errorlevel 1 ( pause & goto menu )
set "CAM=webcam0"
goto subir

:live_video
cls
echo --- CELULAR + VIDEO POR CIMA ---
echo.
echo Abra o Iriun no celular e no PC antes de continuar.
echo.
pause
call :escolher
if errorlevel 1 goto menu
echo.
echo Video no canto [C] ou cobrindo a tela toda [T]?
set "modo="
set /p "modo=Escolha (C/T): "
if /i "%modo%"=="T" (
    python "%CAMVIDEO%" "%ESCOLHIDO%" --live --sobre cheio
) else (
    python "%CAMVIDEO%" "%ESCOLHIDO%" --live
)
if errorlevel 1 ( pause & goto menu )
set "CAM=webcam0"
goto subir

:sintetica
set "CAM=emulated"
goto subir

rem ---------------------------------------------------------------- subir
:subir
echo.
if not "%CAM%"=="emulated" (
    echo ATENCAO: no OBS, ligue a saida uma vez por sessao:
    echo    Ferramentas ^> DroidCam Virtual Output ^> Start
    echo.
    pause
)
echo Encerrando emulador anterior e limpando locks...
"%ADB%" -s emulator-5554 emu kill >nul 2>&1
timeout /t 6 /nobreak >nul
del /q "%USERPROFILE%\.android\avd\%AVD%.avd\*.lock" >nul 2>&1
rmdir /s /q "%USERPROFILE%\.android\avd\%AVD%.avd\hardware-qemu.ini.lock" >nul 2>&1
rmdir /s /q "%USERPROFILE%\.android\avd\%AVD%.avd\multiinstance.lock" >nul 2>&1

echo Subindo o emulador (traseira = %CAM%)...
"%EMU%" -avd %AVD% -no-snapshot -timezone America/Sao_Paulo -camera-back %CAM% -camera-front emulated -gpu auto
goto menu
