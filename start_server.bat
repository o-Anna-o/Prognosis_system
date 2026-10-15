@echo off
chcp 65001 >nul
setlocal
title Прогноз цен на недвижимость — сервер
cd /d "%~dp0"

echo Сайт: http://127.0.0.1:5000
echo Закройте окно, чтобы остановить сервер.
echo.

rem Останавливаем старый процесс на порту 5000, если он есть
netstat -ano | findstr ":5000" | findstr "LISTENING" >nul
if %errorlevel%==0 (
    echo Порт 5000 занят — останавливаю старый процесс...
    for /f "tokens=5" %%p in ('netstat -ano ^| findstr ":5000" ^| findstr "LISTENING"') do taskkill /F /PID %%p >nul 2>&1
    timeout /t 2 /nobreak >nul
)

:restart
echo [%date% %time%] Запуск сервера...
".venv\Scripts\python.exe" web_app\app.py
echo [%date% %time%] Сервер остановлен (код %errorlevel%). Перезапуск через 3 сек...
timeout /t 3 /nobreak >nul
goto restart
