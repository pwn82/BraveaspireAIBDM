@echo off
echo ==========================================
echo   BraveAspire AI BDM Agent - Full Stack
echo ==========================================
echo.

:: Verify Python is accessible
python --version >nul 2>&1
if errorlevel 1 (
    echo ERROR: python not found on PATH.
    echo Make sure Python 3.13 is installed and on your PATH.
    pause
    exit /b 1
)

echo Starting FastAPI backend on :8000 ...
start "BraveAspire API" cmd /k "cd /d "%~dp0" && python -m uvicorn backend.main:app --host 0.0.0.0 --port 8000 --reload"

timeout /t 3 /nobreak >nul

echo Starting Streamlit on :8501 ...
start "BraveAspire UI" cmd /k "cd /d "%~dp0" && python -m streamlit run streamlit_app.py --server.port 8501"

echo.
echo Both services starting...
echo   Streamlit UI : http://localhost:8501
echo   FastAPI API  : http://localhost:8000
echo   API Docs     : http://localhost:8000/docs
echo.
pause
