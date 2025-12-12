@echo off
REM Try to set UTF-8 encoding, ignore if it fails
chcp 65001 >nul 2>&1

title Discord Stock Bot

echo ========================================
echo   Discord Stock Bot
echo ========================================
echo.

REM Change to script directory
cd /d "%~dp0"

REM Clear Python environment variables to avoid conflicts
set PYTHONHOME=
set PYTHONPATH=

REM Fix Tcl/Tk library path for Python 3.13 (prevents tkinter init.tcl error)
REM Find Python path and set TCL_LIBRARY and TK_LIBRARY
for /f "tokens=*" %%i in ('py -c "import sys; import os; print(os.path.dirname(sys.executable))" 2^>nul') do set PYTHON_DIR=%%i
if defined PYTHON_DIR (
    if exist "%PYTHON_DIR%\tcl\tcl8.6" (
        set TCL_LIBRARY=%PYTHON_DIR%\tcl\tcl8.6
        set TK_LIBRARY=%PYTHON_DIR%\tcl\tk8.6
    )
)

echo.

REM Check .env file
if not exist ".env" (
    echo [WARNING] .env file is missing!
    echo Please create .env file by referring to env_example.txt
    echo.
    echo Press any key to exit...
    pause >nul
    exit /b 1
)

echo [2/3] .env file found
echo.

REM Check and install required packages
echo [3/3] Checking required packages...

REM Check Python installation
py --version >nul 2>&1
if %errorlevel% neq 0 (
    echo [ERROR] Python not found. Please install Python from python.org
    echo Press any key to exit...
    pause >nul
    exit /b 1
)

REM Get Python executable path
for /f "tokens=*" %%i in ('py -c "import sys; print(sys.executable)" 2^>nul') do set PYTHON_EXE=%%i
if not defined PYTHON_EXE (
    echo [ERROR] Python installation may be corrupted.
    echo Please reinstall Python from python.org
    echo.
    echo Press any key to exit...
    pause >nul
    exit /b 1
)

REM Check for virtual environment, create if not exists
if not exist "venv" (
    echo Creating virtual environment...
    py -m venv venv
    if errorlevel 1 (
        echo [ERROR] Failed to create virtual environment.
        echo Please reinstall Python from python.org
        echo Make sure to check "Add Python to PATH" and "tcl/tk and IDLE" during installation.
        echo.
        echo Press any key to exit...
        pause >nul
        exit /b 1
    )
    echo Virtual environment created.
)

REM Activate virtual environment
echo Activating virtual environment...
call venv\Scripts\activate.bat
if errorlevel 1 (
    echo [ERROR] Failed to activate virtual environment.
    echo Press any key to exit...
    pause >nul
    exit /b 1
)
echo Virtual environment activated.
echo.

REM Install packages in virtual environment
echo Installing required packages (this may take a few minutes)...
echo.
pip install -r requirements.txt --no-warn-script-location
if errorlevel 1 (
    echo.
    echo [ERROR] Failed to install packages.
    echo Please check requirements.txt file.
    echo.
    echo Press any key to exit...
    pause >nul
    exit /b 1
)
echo Packages checked
echo.

REM Start bot
echo ========================================
echo   Starting bot...
echo ========================================
echo.

python main.py

REM Handle errors
if errorlevel 1 (
    echo.
    echo ========================================
    echo   Error occurred while running bot
    echo ========================================
    echo.
    echo Please check the following:
    echo 1. Verify DISCORD_TOKEN and DISCORD_CHANNEL_ID in .env file
    echo 2. Check internet connection
    echo 3. Check bot.log file for detailed error messages
    echo.
    echo Press any key to exit...
    pause >nul
    exit /b 1
)

echo.
echo Press any key to exit...
pause >nul

