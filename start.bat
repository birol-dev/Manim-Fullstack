@echo off
setlocal
title Manim Studio
cd /d "%~dp0"
py -3 -c "import sys" >nul 2>nul
if not errorlevel 1 (
    py -3 run.py %*
    goto finished
)
python -c "import sys" >nul 2>nul
if not errorlevel 1 (
    python run.py %*
    goto finished
)
echo.
echo Python was not found on this PC.
echo Install Python 3.11 or newer from https://www.python.org/downloads/
echo and tick "Add python.exe to PATH" during setup, then double-click this file again.
echo.
pause
exit /b 1
:finished
if errorlevel 1 (
    echo.
    echo Manim Studio stopped with an error. The text above says what to fix.
    pause
)
exit /b %errorlevel%
