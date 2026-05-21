@echo off
echo ==========================================
echo   BraveAspire AI BDM Agent
echo ==========================================
echo.
echo Starting Streamlit app on http://localhost:8501 ...
python -m streamlit run streamlit_app.py --server.port 8501
pause
