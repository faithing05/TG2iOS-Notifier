@echo off
setlocal

pyinstaller -y --noconsole --exclude-module PySide6 --name TgIosNotifier desktop_app.py

endlocal
