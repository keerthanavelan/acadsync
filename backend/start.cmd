@echo off
cd /d "%~dp0"
if exist ".venv-acadsync\Scripts\python.exe" (
  ".venv-acadsync\Scripts\python.exe" -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --no-access-log
) else (
  ".venv\Scripts\python.exe" -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --no-access-log
)
