@echo off
setlocal
powershell -ExecutionPolicy Bypass -File "%~dp0serve.ps1" -Port 8000
