@echo off
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  py -3 -m venv .venv
  if errorlevel 1 goto error
)
".venv\Scripts\python.exe" -c "import tkinter, PIL, sounddevice" >nul 2>&1
if errorlevel 1 (
  ".venv\Scripts\python.exe" -m pip install -r windows-requirements.txt
  if errorlevel 1 goto error
)
".venv\Scripts\python.exe" desktop.py
if errorlevel 1 goto error
exit /b 0
:error
echo.
echo Timo Remote could not start. Keep this window open and send the error message.
pause
