@echo off
REM =====================================================
REM  YGO AI Assistant - Build (single .exe)
REM =====================================================
REM 打完会在 dist\ygo-assistant.exe（约 80-120 MB）
REM 用户只需要这一个文件 + 配 .env 即可，不需要装 Python

setlocal
cd /d "%~dp0"

if not exist "logs" mkdir logs
set LOGFILE=logs\build.log
echo. > %LOGFILE%

echo ===================================================== >> %LOGFILE%
echo Build started at %DATE% %TIME% >> %LOGFILE%
echo ===================================================== >> %LOGFILE%

echo.
echo =====================================================
echo  YGO AI Assistant - Build Single .exe
echo =====================================================
echo.

where python >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Python not found.
    pause
    exit /b 1
)

echo [1/4] Installing PyInstaller (Tsinghua mirror) ...
python -m pip install --quiet pyinstaller -i https://pypi.tuna.tsinghua.edu.cn/simple >> %LOGFILE% 2>&1
if errorlevel 1 (
    echo [WARN] Tsinghua failed, retrying default ...
    python -m pip install --quiet pyinstaller >> %LOGFILE% 2>&1
)
echo       Done.

echo.
echo [2/4] Cleaning previous build ...
if exist "dist" rmdir /S /Q "dist"
if exist "build" rmdir /S /Q "build"

echo.
echo [3/4] Building with PyInstaller (this takes 2-5 minutes) ...
python -m PyInstaller main.spec --clean --noconfirm >> %LOGFILE% 2>&1
if errorlevel 1 (
    echo [ERROR] PyInstaller failed. See %LOGFILE%
    type %LOGFILE% | findstr /C:"error" /C:"Error"
    pause
    exit /b 1
)

echo.
echo [4/4] Verifying ...
if exist "dist\ygo-assistant.exe" (
    for %%A in ("dist\ygo-assistant.exe") do (
        set SIZE=%%~zA
    )
    echo.
    echo =====================================================
    echo  [OK] ygo-assistant.exe built.
    echo       Path: %CD%\dist\ygo-assistant.exe
    echo =====================================================
) else (
    echo [ERROR] dist\ygo-assistant.exe not found.
    type %LOGFILE% | findstr /C:"error" /C:"Error"
)

echo.
echo Build log: %LOGFILE%
echo.
pause
