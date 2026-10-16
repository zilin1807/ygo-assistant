@echo off
REM =====================================================
REM  YGO AI Assistant - Release Package Builder
REM  Packs: ygo-assistant.exe + .env.example + usage.txt
REM  Output: release\ygo-assistant-v1.0.zip
REM =====================================================

setlocal
cd /d "%~dp0"

set VER=1.0
set OUTDIR=release
set PKGDIR=%OUTDIR%\ygo-assistant-v%VER%
set ZIP=%OUTDIR%\ygo-assistant-v%VER%.zip

where powershell >nul 2>&1
if errorlevel 1 (
    echo [ERROR] PowerShell not found (needed for zip).
    pause
    exit /b 1
)

if not exist "dist\ygo-assistant.exe" (
    echo [ERROR] dist\ygo-assistant.exe not found.
    echo        Run build.bat first to build the exe.
    pause
    exit /b 1
)

echo.
echo =====================================================
echo   YGO AI Assistant - Release Package
echo   Version: 1.0
echo =====================================================
echo.

REM ---- Clean previous ----
if exist "%OUTDIR%" rmdir /S /Q "%OUTDIR%"
mkdir "%PKGDIR%"

REM ---- Copy exe ----
echo [1/4] Copying exe ...
copy /Y "dist\ygo-assistant.exe" "%PKGDIR%\" >nul
echo       ygo-assistant.exe

REM ---- Copy .env.example ----
echo [2/4] Copying config template ...
copy /Y ".env.example" "%PKGDIR%\.env.example" >nul

REM ---- Write usage.txt (no %VARS% inside parens) ----
echo [3/4] Writing usage.txt ...
set USAGE=%PKGDIR%\usage.txt
echo YGO AI Assistant v1.0 - Quick Start >  "%USAGE%"
echo.                                            >> "%USAGE%"
echo ------------------------------------------------------------ >> "%USAGE%"
echo 1. Get an API Key >> "%USAGE%"
echo ------------------------------------------------------------ >> "%USAGE%"
echo Visit https://dashscope.aliyun.com/ to register and create >> "%USAGE%"
echo an API Key. Models to enable for free trial: >> "%USAGE%"
echo   - qwen-vl-ocr-2025-11-20  (vision) >> "%USAGE%"
echo   - qwen-max                 (decision) >> "%USAGE%"
echo   - qwen-flash or qwen-turbo (optional, lighter chat) >> "%USAGE%"
echo. >> "%USAGE%"
echo ------------------------------------------------------------ >> "%USAGE%"
echo 2. Configure >> "%USAGE%"
echo ------------------------------------------------------------ >> "%USAGE%"
echo Copy .env.example to .env: >> "%USAGE%"
echo     copy .env.example .env >> "%USAGE%"
echo. >> "%USAGE%"
echo Open .env and paste your DASHSCOPE_API_KEY. >> "%USAGE%"
echo. >> "%USAGE%"
echo ------------------------------------------------------------ >> "%USAGE%"
echo 3. Run >> "%USAGE%"
echo ------------------------------------------------------------ >> "%USAGE%"
echo Double-click ygo-assistant.exe. >> "%USAGE%"
echo. >> "%USAGE%"
echo On first launch: >> "%USAGE%"
echo   - A small desktop pet appears in the top-left >> "%USAGE%"
echo   - It speaks every 8-25 seconds (companion mode) >> "%USAGE%"
echo   - When Master Duel starts, it auto-switches to >> "%USAGE%"
echo     analysis mode with a chat panel beside the pet >> "%USAGE%"
echo   - Click "adopt" / "ignore" to give feedback >> "%USAGE%"
echo. >> "%USAGE%"
echo ------------------------------------------------------------ >> "%USAGE%"
echo Troubleshooting >> "%USAGE%"
echo ------------------------------------------------------------ >> "%USAGE%"
echo - Windows Defender may flag this as new/unknown on first run. >> "%USAGE%"
echo   Right-click - Properties - Unblock - Run anyway. >> "%USAGE%"
echo - If the pet does not appear, ensure you have VC++ Redistributable >> "%USAGE%"
echo   installed (Win10/11 usually have it built-in). >> "%USAGE%"
echo - Logs are written to %%APPDATA%%\ygo-assistant\runtime.log >> "%USAGE%"
echo   Share this if you need support. >> "%USAGE%"
echo. >> "%USAGE%"

REM ---- Zip ----
echo [4/4] Zipping ...
powershell -Command "Compress-Archive -Path '%PKGDIR%\*' -DestinationPath '%ZIP%' -Force"

if not exist "%ZIP%" (
    echo [ERROR] zip failed.
    pause
    exit /b 1
)

echo.
echo =====================================================
echo [OK] Release package ready.
echo      Path: %CD%\%ZIP%
echo =====================================================
echo.
echo Contents of %PKGDIR%:
dir "%PKGDIR%" /B
echo.
echo Zip size:
for %%A in ("%ZIP%") do echo      %%~zA bytes
echo.
pause
