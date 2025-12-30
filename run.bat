@echo off
chcp 65001 > nul
cd /d "%~dp0"
python prompt_picker.py "AIを使って考えるための全技術.md"
pause
