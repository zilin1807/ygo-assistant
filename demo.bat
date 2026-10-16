@echo off
REM =====================================================
REM  YGO AI Assistant - Demo (no GUI required)
REM  Run a high-fidelity Master Duel scene through vision + decision,
REM  and print what the floating widget WOULD display.
REM =====================================================

setlocal
cd /d "%~dp0"

where python >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Python not found in PATH.
    pause
    exit /b 1
)

if not exist ".env" (
    copy /Y .env.example .env >nul
    echo [.env created] Please set DASHSCOPE_API_KEY in .env, then run this again.
    notepad .env
    pause
    exit /b 1
)

echo Installing minimal deps for demo (dashscope, Pillow)...
python -m pip install --quiet dashscope Pillow python-dotenv

echo.
echo Running demo (vision + decision on a synthetic MD battle scene)...
echo.
python demo.py

echo.
pause
