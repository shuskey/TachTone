@echo off
setlocal

echo ============================================
echo  TachTone Installer Build
echo ============================================
echo.

:: ---- PyInstaller ----
echo [1/2] Building standalone app with PyInstaller...
pyinstaller tacktone.spec --noconfirm
if errorlevel 1 (
    echo.
    echo ERROR: PyInstaller build failed.
    echo Make sure PyInstaller is installed: pip install pyinstaller
    goto :fail
)
echo PyInstaller done.
echo.

:: ---- Inno Setup ----
echo [2/2] Building Windows installer with Inno Setup...

set ISCC="C:\Program Files (x86)\Inno Setup 6\ISCC.exe"
if not exist %ISCC% (
    echo ERROR: Inno Setup 6 not found at %ISCC%
    echo Download from: https://jrsoftware.org/isinfo.php
    goto :fail
)

%ISCC% installer\tacktone.iss
if errorlevel 1 (
    echo.
    echo ERROR: Inno Setup build failed.
    goto :fail
)

echo.
echo ============================================
echo  SUCCESS
echo  Installer: installer\Output\TachTone_Setup.exe
echo ============================================
goto :end

:fail
echo.
echo BUILD FAILED.
exit /b 1

:end
endlocal
