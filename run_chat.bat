@echo off
rem Double-click to start chatting with the customer service bot.
rem Starts Ollama automatically if it is not running.
rem This file is pure ASCII on purpose: cmd.exe mis-reads Chinese text in .bat files.
cd /d "%~dp0"
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\menu.ps1" 1
pause
