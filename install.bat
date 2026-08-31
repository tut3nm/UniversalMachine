@echo off
REM ============================================================================
REM  install.bat  -  Instala las dependencias del sistema web (backend +
REM                  frontend). Correr una sola vez (o de nuevo si cambiaron
REM                  requirements.txt / package.json).
REM ============================================================================
setlocal
cd /d "%~dp0"

set "PYEXE="
where py >nul 2>nul && set "PYEXE=py -3"
if not defined PYEXE where python >nul 2>nul && set "PYEXE=python"

if not defined PYEXE (
  echo [ERROR] No se encontro Python 3 en el sistema.
  echo Instalalo desde https://www.python.org/downloads/  ^(marca "Add to PATH"^)
  pause
  exit /b 1
)

where node >nul 2>nul
if errorlevel 1 (
  echo [ERROR] No se encontro Node.js en el sistema.
  echo Instalalo desde https://nodejs.org/  y volve a ejecutar este archivo.
  pause
  exit /b 1
)

echo === Backend: creando entorno virtual (backend\.venv) ===
if not exist "backend\.venv" (
  %PYEXE% -m venv "backend\.venv"
  if errorlevel 1 (
    echo [ERROR] No se pudo crear el entorno virtual.
    pause
    exit /b 1
  )
)

echo === Backend: instalando dependencias (FastAPI, uvicorn, pywebview, etc.) ===
"backend\.venv\Scripts\python.exe" -m pip install --upgrade pip --quiet
"backend\.venv\Scripts\python.exe" -m pip install -r "backend\requirements.txt"
if errorlevel 1 (
  echo [ERROR] No se pudieron instalar las dependencias del backend.
  pause
  exit /b 1
)

echo.
echo === Frontend: instalando dependencias (npm install) ===
pushd "front"
call npm install
if errorlevel 1 (
  echo [ERROR] No se pudieron instalar las dependencias del frontend.
  popd
  pause
  exit /b 1
)
popd

echo.
echo ============================================================================
echo  LISTO. Dependencias instaladas.
echo    - Backend:  backend\.venv\
echo    - Frontend: front\node_modules\
echo  Ahora podes usar run.bat para levantar el sistema en modo desarrollo,
echo  o build.bat para generar el ejecutable empaquetado.
echo ============================================================================
pause
endlocal
