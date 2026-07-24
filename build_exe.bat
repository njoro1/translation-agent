@echo off
REM Build a standalone Windows executable for the GUI.
REM Output: dist\TranslationAgent.exe  (debug.log is written next to it at runtime)
pyinstaller --noconfirm --onefile --windowed --name TranslationAgent --collect-all PySide6 --add-data "ui;ui" main.py
