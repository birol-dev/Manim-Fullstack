@echo off
title Manim Composer & Editor
echo Launching Manim Composer...
python run.py
if %ERRORLEVEL% neq 0 (
    echo.
    echo Error: Failed to start Manim Composer. Please verify Python is installed and in your PATH.
    pause
)
