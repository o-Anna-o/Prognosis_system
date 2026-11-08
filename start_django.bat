@echo off
chcp 65001 >nul
setlocal
cd /d "%~dp0"
".venv\Scripts\python.exe" backend\manage.py runserver 127.0.0.1:8000
