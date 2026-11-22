@echo off
title I.R.I.S. v2.5 — Physical Hardware Diagnostics
color 0B
echo ======================================================================
echo    I.R.I.S. v2.5 — ESP32 Physical Hardware Component Test Suite
echo ======================================================================
echo.
python test_hardware_interactive.py
echo.
echo ======================================================================
echo Test finished. Press any key to exit...
pause >nul
