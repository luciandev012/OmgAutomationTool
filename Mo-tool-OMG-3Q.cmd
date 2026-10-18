@echo off
set "PYTHONW=%~dp0.venv\Scripts\pythonw.exe"
if not exist "%PYTHONW%" (
  echo Chua co moi truong chay. Hay mo Cai-dat.cmd truoc.
  pause
  exit /b 1
)
start "" "%PYTHONW%" "%~dp0omg3q_tool.py"
