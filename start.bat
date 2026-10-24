@echo off
cd /d %~dp0
set HF_HUB_DISABLE_SYMLINKS_WARNING=1
start "" .venv\Scripts\pythonw.exe -W ignore app.py

