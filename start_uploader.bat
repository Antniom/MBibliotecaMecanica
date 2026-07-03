@echo off
title Painel de Ingestão — MBibliotecaMecânica
echo A iniciar o Painel de Ingestão da Super-Biblioteca...
echo.

:: Check python virtual environment exists
if not exist venv\Scripts\python.exe (
    echo Erro: O ambiente virtual Python não foi encontrado em .\venv.
    echo Por favor, garante que executaste a configuração inicial.
    pause
    exit /b
)

:: Run Ingestion UI App
venv\Scripts\python pipeline\uploader_app.py

pause
