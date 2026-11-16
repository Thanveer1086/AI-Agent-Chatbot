@echo off
setlocal enabledelayedexpansion

echo ========================================================
echo AI-Agent-ChatBot: PostgreSQL + pgvector Database Backup
echo ========================================================

:: Ensure backups folder exists
if not exist "backups" mkdir "backups"

:: Generate clean ISO-like timestamp using PowerShell
for /f "usebackq tokens=*" %%a in (`powershell -NoProfile -Command "Get-Date -Format 'yyyyMMdd_HHmmss'"`) do set TIMESTAMP=%%a

if "%TIMESTAMP%"=="" set TIMESTAMP=%date:~-4%%date:~4,2%%date:~7,2%_%time:~0,2%%time:~3,2%
set TIMESTAMP=%TIMESTAMP: =0%

set BACKUP_FILE=backups\backup_agent_chatbot_%TIMESTAMP%.sql

echo Exporting PostgreSQL tables and pgvector indexes from 'agent_chatbot_db'...
docker exec -t agent_chatbot_db pg_dump -U postgres agent_chatbot > "%BACKUP_FILE%"

if %ERRORLEVEL% EQU 0 (
    echo.
    echo ========================================================
    echo [SUCCESS] Database backup created successfully!
    echo File: %BACKUP_FILE%
    echo ========================================================
) else (
    echo.
    echo [ERROR] Backup failed. Verify that 'agent_chatbot_db' container is running.
)
