@echo off
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" py -3 -m venv .venv
if errorlevel 1 goto end
".venv\Scripts\python.exe" -m pip install -r windows-requirements.txt pyinstaller
if errorlevel 1 goto end
set TIMO_APK_DATA=
if exist "apks\TimoRemote-Robot.apk" set TIMO_APK_DATA=--add-data "apks;apks"
".venv\Scripts\python.exe" -m PyInstaller --noconfirm --clean --onefile --windowed --name TimoRemoteWindows --add-data "web;web" %TIMO_APK_DATA% --add-data "face-preview;face-preview" --collect-all sounddevice --hidden-import _cffi_backend desktop.py
:end
pause
