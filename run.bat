@echo off
REM Vaithuhayho Web App - Start Script

echo ================================
echo  Vaithuhayho Web Application
echo  Starting server...
echo ================================
echo.

REM Check if Python is installed
python --version >nul 2>&1
if errorlevel 1 (
    echo ERROR: Python is not installed or not in PATH
    echo Please install Python 3.8+ from https://www.python.org/
    pause
    exit /b 1
)

REM Check if virtual environment exists
if not exist "venv\" (
    echo Virtual environment not found. Creating...
    python -m venv venv
    echo.
)

REM Activate virtual environment
call venv\Scripts\activate.bat

REM Check if requirements are installed
pip show flask >nul 2>&1
if errorlevel 1 (
    echo Installing dependencies...
    pip install -r requirements.txt
    echo.
)

REM Check if Firebase credentials exist
if not exist "handover-4.json" (
    echo WARNING: Firebase credentials file 'handover-4.json' not found
    echo The app may not work properly without Firebase configuration
    echo.
)

REM Start the application in development mode (auto-reload enabled)
echo Starting Flask server in DEV MODE (auto-reload enabled)...
echo.
echo Server will be available at: http://127.0.0.1:9090
echo Server will AUTO-RELOAD when you change HTML/Python files
echo Press Ctrl+C to stop the server
echo.

python app.py --dev

pause
