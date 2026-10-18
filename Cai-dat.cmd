@echo off
set "PYTHON=%LOCALAPPDATA%\Programs\Python\Python311\python.exe"
if not exist "%PYTHON%" (
  echo Khong tim thay Python 3.11.
  pause
  exit /b 1
)
if not exist "%~dp0.venv\Scripts\python.exe" (
  "%PYTHON%" -m venv "%~dp0.venv"
  if errorlevel 1 exit /b 1
)
"%~dp0.venv\Scripts\python.exe" -m pip install -r "%~dp0requirements.txt"
if errorlevel 1 (
  pause
  exit /b 1
)
echo Da cai dat xong. Mo Mo-tool-OMG-3Q.cmd de chay.
pause
