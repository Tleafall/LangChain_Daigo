@echo off
rem Double-click to run the demo (4 preset questions, no typing needed).
rem Starts Ollama automatically if it is not running.
rem This file is pure ASCII on purpose: cmd.exe mis-reads Chinese text in .bat files.
cd /d "%~dp0"
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\menu.ps1" 2
pause
