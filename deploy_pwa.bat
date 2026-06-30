@echo off
powershell -ExecutionPolicy Bypass -File "%~dp0deploy_pwa.ps1" %*
