@echo off
chcp 65001 > nul
cd /d "%~dp0"
python prompt_picker_gui.py
pause
