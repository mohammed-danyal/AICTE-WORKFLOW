@echo off
cd /d "%~dp0"
set "PORTAL_PYTHON=C:\Users\siddh\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe"
if exist "%PORTAL_PYTHON%" (
  "%PORTAL_PYTHON%" server.py
) else (
  py -3 server.py
)
pause
