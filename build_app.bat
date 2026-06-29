@echo off
setlocal

pyinstaller -y --clean --onefile --noconsole --exclude-module PySide6 --name TgIosNotifier desktop_app.py

endlocal
