@echo off
chcp 65001 >nul
cd /d "%~dp0"
rem O banco fica fora do OneDrive para nao corromper durante a sincronizacao.
if not defined POUSADA_DB set "POUSADA_DB=%LOCALAPPDATA%\Pousada\reservas.db"
if not exist "%LOCALAPPDATA%\Pousada" mkdir "%LOCALAPPDATA%\Pousada"
echo ===Pousada Boa Esperanca - Sistema de Reservas ===
where python >nul 2>nul
if errorlevel 1 (
  echo Python nao encontrado. Instale em https://www.python.org/downloads/ marcando "Add Python to PATH".
  pause
  exit /b 1
)
if not exist venv (
  echo Criando ambiente virtual - so na primeira vez...
  python -m venv venv
)
call venv\Scripts\activate.bat
echo Instalando dependencias...
pip install -q -r requirements.txt
echo.
echo Abrindo o sistema. Deixe esta janela aberta enquanto usa.
start "" http://localhost:5000
python app.py
pause
