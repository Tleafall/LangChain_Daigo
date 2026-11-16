@echo off
rem ============================================================
rem  Double-click to open the main menu (chat / demo / sync / lessons).
rem  This file is pure ASCII on purpose: cmd.exe mis-reads Chinese text in .bat files.
rem  The real menu (with Chinese text) is scripts\menu.ps1.
rem  Optional: start.bat 1  -> skip the menu and run option 1 directly.
rem ============================================================
cd /d "%~dp0"
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\menu.ps1" %1
pause
