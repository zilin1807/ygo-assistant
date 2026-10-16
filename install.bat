@echo off
REM =====================================================
REM  YGO AI Assistant - Install Dependencies (robust)
REM  All output is ALSO written to logs\install.log
REM  so even if the cmd window closes you can read it.
REM =====================================================

setlocal
cd /d "%~dp0"
set TUNA=https://pypi.tuna.tsinghua.edu.cn/simple

REM ---- redirect all output to log AND console ----
if not exist "logs" mkdir logs
echo. > logs\install.log
set LOGFILE=logs\install.log

REM Tee wrapper: any command's output -> %LOGFILE% via ">> ... 2>&1"
REM Manually echo each step into the file (much safer than weird tees in cmd).

echo ===================================================== > %LOGFILE%
echo   YGO AI Assistant - Install Dependencies (robust) >> %LOGFILE%
echo ===================================================== >> %LOGFILE%
echo. >> %LOGFILE%
echo Started at %DATE% %TIME% >> %LOGFILE%
echo. >> %LOGFILE%

echo.
echo =====================================================
echo   YGO AI Assistant - Install Dependencies (robust)
echo =====================================================
echo. Log: %LOGFILE%
echo.

REM ---- check Python ----
echo [0/5] Checking Python...
where python
if errorlevel 1 (
    echo [ERROR] Python not found in PATH. >> %LOGFILE%
    echo [ERROR] Python not found in PATH.
    echo Please install Python 3.11+ and tick "Add to PATH".
    pause
    exit /b 1
)
echo Python found. >> %LOGFILE%

REM ---- record python version ----
python --version >> %LOGFILE% 2>&1

REM ---- upgrade pip (best-effort) ----
echo.
echo [1/5] Upgrading pip via Tsinghua mirror...
echo. >> %LOGFILE%
echo [1/5] Upgrading pip via Tsinghua mirror >> %LOGFILE%
python -m pip install --upgrade pip -i %TUNA% >> %LOGFILE% 2>&1
if errorlevel 1 (
    echo [WARN] pip upgrade failed via Tsinghua, retrying default... >> %LOGFILE%
    python -m pip install --upgrade pip >> %LOGFILE% 2>&1
)

REM ---- install requirements.txt ----
echo.
echo [2/5] Installing from requirements.txt (Tsinghua mirror first)...
echo       PySide6 alone is ~100MB, this step can take several minutes.
echo.
echo [2/5] Installing from requirements.txt >> %LOGFILE%
python -m pip install -r requirements.txt -i %TUNA% >> %LOGFILE% 2>&1
if errorlevel 1 (
    echo.
    echo [WARN] Tsinghua mirror failed, retrying default pypi.org...
    echo [WARN] Tsinghua failed, retrying default. >> %LOGFILE%
    python -m pip install -r requirements.txt >> %LOGFILE% 2>&1
)

REM ---- verify one by one (clearer error) ----
echo.
echo [3/5] Verifying PySide6...
echo [3/5] Verifying PySide6 >> %LOGFILE%
python -c "import PySide6; print('PySide6', PySide6.__version__)" 2>>%LOGFILE%
if errorlevel 1 (
    echo [FAIL] PySide6 not importable.
    echo [FAIL] PySide6 not importable. See %LOGFILE% >> %LOGFILE%
    echo        Try: pip install -i %TUNA% PySide6
) else (
    echo [OK] PySide6.
)

echo.
echo [4/5] Verifying mss...
echo [4/5] Verifying mss >> %LOGFILE%
python -c "import mss; print('mss', mss.__version__)" 2>>%LOGFILE%
if errorlevel 1 (
    echo [FAIL] mss not importable.
) else (
    echo [OK] mss.
)

echo.
echo [5/5] Verifying dashscope / Pillow / dotenv...
echo [5/5] Verifying others >> %LOGFILE%
python -c "import dashscope, PIL, dotenv; print('all OK')" 2>>%LOGFILE%
if errorlevel 1 (
    echo [FAIL] Some non-GUI packages missing.
) else (
    echo [OK] All non-GUI packages.
)

echo.
echo =====================================================
echo Full log saved to: %LOGFILE%
echo (If cmd closed, you can read this file instead.)
echo =====================================================
echo. >> %LOGFILE%
echo Finished at %DATE% %TIME% >> %LOGFILE%
echo.
pause
