@echo off
echo ==========================================
echo   BraveAspire FastAPI Backend
echo   Running on http://localhost:8000
echo   API Docs: http://localhost:8000/docs
echo ==========================================
python -m uvicorn backend.main:app --host 0.0.0.0 --port 8000 --reload
pause
