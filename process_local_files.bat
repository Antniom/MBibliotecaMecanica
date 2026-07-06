@echo off
title MBibliotecaMecanica — Processar Ficheiros Locais
color 0B
echo.
echo  =====================================================
echo   MBibliotecaMecanica — Processar Ficheiros Locais
echo  =====================================================
echo.
echo  Este programa processa todos os ficheiros que estao
echo  atualmente colocados na pasta local 'entrada/'.
echo.
echo  Depois de processar, ele ira enviar automaticamente
echo  as novas paginas para o site.
echo.
echo  =====================================================
echo.

cd /d "%~dp0"

if not exist "venv\Scripts\activate.bat" (
    echo ERRO: Ambiente virtual nao encontrado em venv\
    pause
    exit /b 1
)

call venv\Scripts\activate.bat

python pipeline\run_pipeline.py

echo.
echo  Processamento concluido! Prima qualquer tecla para fechar.
pause > nul
