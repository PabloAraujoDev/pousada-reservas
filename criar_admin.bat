@echo off
chcp 65001 >nul
cd /d "%~dp0"
rem Cria o primeiro administrador no MESMO banco que o iniciar.bat usa.
if not defined POUSADA_DB set "POUSADA_DB=%LOCALAPPDATA%\Pousada\reservas.db"
if not exist "%LOCALAPPDATA%\Pousada" mkdir "%LOCALAPPDATA%\Pousada"
echo === Criar administrador - Pousada Boa Esperanca ===
echo Banco: %POUSADA_DB%
echo A senha precisa ter pelo menos 10 caracteres e nao aparece enquanto voce digita.
echo.
if exist venv\Scripts\activate.bat call venv\Scripts\activate.bat
python app.py criar-admin
echo.
pause
