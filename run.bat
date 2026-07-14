@echo off
REM ============================================================================
REM  run.bat  -  Ejecuta el Configurador Maquina 232 desde el codigo fuente.
REM             Modo desarrollo: abre la app usando el Python instalado.
REM ============================================================================
setlocal
cd /d "%~dp0"

set "PYEXE="
where py >nul 2>nul && set "PYEXE=py -3"
if not defined PYEXE where python >nul 2>nul && set "PYEXE=python"

if not defined PYEXE (
  echo [ERROR] No se encontro Python 3 en el sistema.
  echo Instalalo desde https://www.python.org/downloads/  ^(marca "Add to PATH"^)
  echo y volve a ejecutar este archivo.
  pause
  exit /b 1
)

echo Verificando dependencias (openpyxl, para "Importar cambios") ...
%PYEXE% -m pip install --quiet openpyxl
if errorlevel 1 (
  echo [AVISO] No se pudo instalar openpyxl. La app abrira igual, pero
  echo         "Importar cambios" no va a funcionar hasta instalarlo.
)

echo Iniciando Configurador Maquina 232 ...
%PYEXE% "src\app.py"
if errorlevel 1 (
  echo.
  echo La aplicacion termino con un error.
  pause
)
endlocal
