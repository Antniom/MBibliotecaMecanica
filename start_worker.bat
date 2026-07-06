@echo off
title MBibliotecaMecanica — Worker de Processamento
color 0A
echo.
echo  =====================================================
echo   MBibliotecaMecanica — Worker de Processamento
echo  =====================================================
echo.
echo  Este programa recebe ficheiros aprovados pelo
echo  administrador e processa-os automaticamente.
echo.
echo  Para parar: feche esta janela ou prima Ctrl+C
echo.
echo  =====================================================
echo.

cd /d "%~dp0"

if not exist "venv\Scripts\activate.bat" (
    echo ERRO: Ambiente virtual nao encontrado em venv\
    echo Certifica-te de que o projecto esta configurado correctamente.
    pause
    exit /b 1
)

call venv\Scripts\activate.bat

python pipeline\worker.py

echo.
echo  Worker terminado. Prima qualquer tecla para fechar.
pause > nul
