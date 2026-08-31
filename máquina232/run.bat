@echo off
REM ============================================================================
REM  run.bat  -  Ejecuta el Configurador de Parametros de Planta desde el
REM             codigo fuente. Modo desarrollo: usa el Python instalado.
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

echo Verificando dependencias (ttkbootstrap, openpyxl) ...
%PYEXE% -m pip install --quiet ttkbootstrap
if errorlevel 1 (
  echo [ERROR] No se pudo instalar ttkbootstrap ^(necesario para la interfaz^).
  pause
  exit /b 1
)
%PYEXE% -m pip install --quiet openpyxl
if errorlevel 1 (
  echo [AVISO] No se pudo instalar openpyxl. La app abrira igual, pero
  echo         "Importar cambios" no va a funcionar hasta instalarlo.
)

echo Iniciando Configurador de Parametros de Planta ...
%PYEXE% "src\app.py"
if errorlevel 1 (
  echo.
  echo La aplicacion termino con un error.
  pause
)
endlocal
