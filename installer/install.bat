@echo off
:: Lead Machine Windows Installer
:: Run this file as Administrator

echo Lead Machine Installation Wizard
echo ==================================
echo.

:: Check Python 3 is available
python3 --version >nul 2>&1
if errorlevel 1 (
    python --version >nul 2>&1
    if errorlevel 1 (
        echo ERROR: Python 3 is required but was not found.
        echo.
        echo Download Python 3.11+ from: https://www.python.org/downloads/
        echo Make sure to check "Add Python to PATH" during installation.
        echo.
        pause
        exit /b 1
    )
    :: Use "python" if "python3" isn't available
    set PYTHON=python
) else (
    set PYTHON=python3
)

:: Check for Administrator privileges
net session >nul 2>&1
if errorlevel 1 (
    echo ERROR: This installer requires Administrator privileges.
    echo.
    echo Right-click install.bat and choose "Run as administrator".
    echo.
    pause
    exit /b 1
)

:: Run the wizard
%PYTHON% installer\wizard.py %*
if errorlevel 1 (
    echo.
    echo Installation failed or was cancelled.
    pause
    exit /b 1
)

echo.
pause
