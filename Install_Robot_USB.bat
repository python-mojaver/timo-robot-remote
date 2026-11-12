@echo off
cd /d "%~dp0"
set "TIMO_ADB=%LOCALAPPDATA%\Android\Sdk\platform-tools\adb.exe"
if not exist "%TIMO_ADB%" (
  echo Android SDK adb.exe was not found. Install using Android Studio or select the APK manually.
  pause
  exit /b 1
)
if not exist "apks\TimoRemote-Robot.apk" (
  echo Build the robot debug APK as described in README.md and copy it into apks first.
  pause
  exit /b 1
)
"%TIMO_ADB%" devices
echo This installs ONLY com.htnhome.timoremote.robot. The main chat app is not replaced.
"%TIMO_ADB%" install -r "apks\TimoRemote-Robot.apk"
if errorlevel 1 goto error
"%TIMO_ADB%" shell am start -n com.htnhome.timoremote.robot/.MainActivity
if errorlevel 1 goto error
echo Robot remote app installed and opened.
pause
exit /b 0
:error
echo Installation did not complete. Check USB authorization and that only the intended robot is connected.
pause
exit /b 1
