@echo off
rem Double-click to sync the latest products and shop rules from yuchingmakeup.com.
rem This file is pure ASCII on purpose: cmd.exe mis-reads Chinese text in .bat files.
cd /d "%~dp0"
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\menu.ps1" 3
pause
