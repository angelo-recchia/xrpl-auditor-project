@echo off
cd /d "%~dp0"
call "%USERPROFILE%\AppData\Local\hermes\hermes-agent\venv\Scripts\activate.bat"
python scripts/run_hybrid_audit.py
pause
