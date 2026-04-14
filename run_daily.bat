@echo off
:: ============================================================
:: Fundament Analyzér – Denní automatický update
:: Spouští se přes Windows Task Scheduler každý den v 21:00
:: (= 19:00 UTC v létě / CEST, 20:00 UTC v zimě / CET)
:: ============================================================

set PROJECT_DIR=d:\Aplikace\fundament analyza
set VENV_PYTHON=%PROJECT_DIR%\venv\Scripts\python.exe
set SCRIPT=%PROJECT_DIR%\backend\scheduler\daily_update.py
set LOG_FILE=%PROJECT_DIR%\logs\daily_update.log

:: Vytvoř složku pro logy pokud neexistuje
if not exist "%PROJECT_DIR%\logs" mkdir "%PROJECT_DIR%\logs"

echo [%DATE% %TIME%] Spoustim Daily Update pipeline... >> "%LOG_FILE%"
"%VENV_PYTHON%" "%SCRIPT%" >> "%LOG_FILE%" 2>&1
echo [%DATE% %TIME%] Pipeline dokoncena. >> "%LOG_FILE%"
