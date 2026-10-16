@echo off
REM =====================================================
REM  YGO AI Assistant - Start (verbose, all output to log)
REM =====================================================

setlocal
cd /d "%~dp0"
set TUNA=https://pypi.tuna.tsinghua.edu.cn/simple

if not exist "logs" mkdir logs
echo. > logs\start.log
set LOGFILE=logs\start.log

REM ---- helper: tee to log file ----
REM Use a tiny subroutine-like approach: we call commands with redirection.

echo ===================================================== > %LOGFILE%
echo   YGO AI Assistant - Start (verbose) >> %LOGFILE%
echo ===================================================== >> %LOGFILE%
echo Started at %DATE% %TIME% >> %LOGFILE%
echo. >> %LOGFILE%

echo.
echo =====================================================
echo   YGO AI Assistant - Start
echo.   Log: %LOGFILE%   (also printed at the end)
echo =====================================================
echo.

REM ---- Python available? ----
echo [0/4] Where python ...
where python >> %LOGFILE% 2>&1
if errorlevel 1 (
    echo [ERROR] Python not in PATH. >> %LOGFILE%
    echo [ERROR] Python not found.
    pause
    exit /b 1
)
python --version >> %LOGFILE% 2>&1

REM ---- deps check, with auto-install as fallback ----
echo.
echo [1/4] Checking dependencies...
echo [1/4] Dep check. >> %LOGFILE%
python -c "import PySide6" 2>nul
if errorlevel 1 (
    echo       PySide6 missing. Installing via Tsinghua...
    echo       Trying pip install. >> %LOGFILE%
    python -m pip install -r requirements.txt -i %TUNA% 1>>%LOGFILE% 2>&1
    if errorlevel 1 (
        echo [ERROR] install failed. See %LOGFILE% >> %LOGFILE%
        echo [ERROR] Install failed. Tail of log:
        powershell -Command "Get-Content '%LOGFILE%' -Tail 30"
        pause
        exit /b 1
    )
)
python -c "import PySide6; print('       PySide6 OK')" 2>>%LOGFILE%
python -c "import mss; print('       mss OK')" 2>>%LOGFILE%
python -c "import dashscope; print('       dashscope OK')" 2>>%LOGFILE%

REM ---- .env ----
echo.
echo [2/4] Checking .env ...
echo [2/4] .env check >> %LOGFILE%
if not exist ".env" (
    echo       .env missing, copying from .env.example.
    copy /Y .env.example .env >nul
    notepad .env
    pause
    exit /b 1
)
echo       OK.

REM ---- Launch master duel reminder ----
echo.
echo [3/4] About to launch main.py
echo       Ensure Master Duel is open (or you'll see a translucent
echo       red screen to drag-select the area).
echo       All output below goes to %LOGFILE%
echo.

python main.py 1>>%LOGFILE% 2>&1
set RC=%errorlevel%

echo.
echo =====================================================
echo [4/4] Python exited with code %RC%
echo.
echo Last 50 lines of log (logs\start.log):
echo ----------------------------------------------------
powershell -Command "Get-Content '%LOGFILE%' -Tail 50"
echo ----------------------------------------------------
echo Full log at: %LOGFILE%
echo =====================================================
echo.

if not "%RC%"=="0" (
    echo [LIKELY FIXES]
    echo   1) "ModuleNotFoundError: No module named '...'"  -^> Run install.bat
    echo   2) "Could not find the Qt platform plugin"      -^> PySide6 broken, reinstall
    echo   3) "Tcl/Tk: cant initialize"                   -^> Tkinter missing, install full Python
    echo   4) Crash silently / black cmd                   -^> Read logs\start.log
)

echo.
pause
