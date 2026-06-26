@echo off
setlocal

pyinstaller -y --noconsole --exclude-module PySide6 --name TgDsNotifier desktop_app.py

endlocal
