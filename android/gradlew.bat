@echo off
setlocal
set "TIMO_JAVA=java.exe"
if defined JAVA_HOME set "TIMO_JAVA=%JAVA_HOME%\bin\java.exe"
"%TIMO_JAVA%" -classpath "%~dp0gradle\wrapper\gradle-wrapper.jar" org.gradle.wrapper.GradleWrapperMain %*
endlocal
