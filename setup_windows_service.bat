@echo off
REM Script para configurar XML Organizer como servico no Windows
REM Requer NSSM (Non-Sucking Service Manager)

echo ==========================================
echo XML Organizer - Configuracao Windows 24/7
echo ==========================================
echo.

REM Verifica se esta rodando como administrador
net session >nul 2>&1
if %errorLevel% neq 0 (
    echo ERRO: Este script precisa ser executado como Administrador!
    echo Clique com botao direito e selecione "Executar como administrador"
    pause
    exit /b 1
)

REM Cria diretorio de dados
echo [1/5] Criando diretorio de dados...
if not exist "C:\xml_organizer_data" mkdir "C:\xml_organizer_data"

REM Baixa NSSM se nao existir
if not exist "nssm.exe" (
    echo [2/5] NSSM nao encontrado!
    echo Por favor, baixe o NSSM de: https://nssm.cc/download
    echo Extraia o nssm.exe para esta pasta e execute novamente.
    pause
    exit /b 1
)

echo [2/5] NSSM encontrado!

REM Encontra Python
echo [3/5] Procurando Python...
where python >nul 2>&1
if %errorLevel% neq 0 (
    echo ERRO: Python nao encontrado no PATH!
    echo Instale Python ou adicione ao PATH do sistema.
    pause
    exit /b 1
)

for /f "tokens=*" %%i in ('where python') do set PYTHON_PATH=%%i
echo Python encontrado: %PYTHON_PATH%

REM Define caminhos
set SCRIPT_PATH=%~dp0xml_organizer.py
echo Script em: %SCRIPT_PATH%

REM Remove servico anterior se existir
echo [4/5] Removendo servico anterior (se existir)...
nssm stop XMLOrganizer >nul 2>&1
nssm remove XMLOrganizer confirm >nul 2>&1

REM Instala o servico
echo [5/5] Instalando servico...
nssm install XMLOrganizer "%PYTHON_PATH%" "%SCRIPT_PATH%"
nssm set XMLOrganizer AppDirectory "%~dp0"
nssm set XMLOrganizer DisplayName "XML Organizer - NF-e/NFC-e"
nssm set XMLOrganizer Description "Processamento automatico de notas fiscais eletronicas"
nssm set XMLOrganizer Start SERVICE_AUTO_START
nssm set XMLOrganizer AppStdout "C:\xml_organizer_data\nssm_stdout.log"
nssm set XMLOrganizer AppStderr "C:\xml_organizer_data\nssm_stderr.log"
nssm set XMLOrganizer AppRotateFiles 1
nssm set XMLOrganizer AppRotateBytes 10485760

REM Inicia o servico
echo.
echo Iniciando servico...
nssm start XMLOrganizer

if %errorLevel% equ 0 (
    echo.
    echo ==========================================
    echo SUCESSO! Servico configurado e iniciado!
    echo ==========================================
    echo.
    echo O XML Organizer agora roda automaticamente em segundo plano.
    echo.
    echo Comandos uteis:
    echo   - Ver status:    nssm status XMLOrganizer
    echo   - Parar:         nssm stop XMLOrganizer
    echo   - Reiniciar:     nssm restart XMLOrganizer
    echo   - Remover:       nssm remove XMLOrganizer confirm
    echo.
    echo Logs em: C:\xml_organizer_data\
    echo.
) else (
    echo.
    echo ERRO ao iniciar o servico!
    echo Verifique os logs em C:\xml_organizer_data\
    echo.
)

pause