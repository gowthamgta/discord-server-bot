@echo off
chcp 65001 > nul
set PYTHONIOENCODING=utf-8
rem The web status page is only for cloud hosts; skipping it avoids a Windows Firewall prompt
set HEALTH_SERVER_DISABLED=1
title Discord Server Manager Bot
cd /d "%~dp0"

echo ===================================================
echo  Starting Discord Server Management Bot...
echo ===================================================

if exist "C:\Users\gotam\AppData\Local\Python\bin\python.exe" (
    "C:\Users\gotam\AppData\Local\Python\bin\python.exe" bot.py
) else (
    python bot.py
)

if %ERRORLEVEL% NEQ 0 (
    echo.
    echo [!] Bot process terminated with error code %ERRORLEVEL%.
    pause
)
