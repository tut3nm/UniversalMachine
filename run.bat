@echo off
REM ============================================================================
REM  run.bat  -  Levanta el sistema en modo desarrollo: backend (FastAPI +
REM             recarga automatica) en una ventana, frontend (Vite) en otra,
REM             y abre el navegador. Requiere haber corrido install.bat antes.
REM ============================================================================
setlocal
cd /d "%~dp0"

if not exist "backend\.venv\Scripts\python.exe" (
  echo [ERROR] No esta instalado el entorno del backend todavia.
  echo Corre install.bat primero.
  pause
  exit /b 1
)
if not exist "front\node_modules" (
  echo [ERROR] No estan instaladas las dependencias del frontend todavia.
  echo Corre install.bat primero.
  pause
  exit /b 1
)

echo Iniciando backend (http://127.0.0.1:8000) ...
start "Configurador de Planta - backend" cmd /k ""backend\.venv\Scripts\python.exe" -m uvicorn app.main:app --reload --app-dir backend --host 127.0.0.1 --port 8000"

echo Iniciando frontend (http://localhost:5173) ...
start "Configurador de Planta - frontend" cmd /k "cd /d "%~dp0front" && npm run dev"

echo.
echo Esperando a que levanten los servidores ...
timeout /t 4 /nobreak >nul
start "" "http://localhost:5173"

echo.
echo ============================================================================
echo  Sistema corriendo en dos ventanas aparte (backend y frontend).
echo  Cerra esas ventanas (o Ctrl+C en cada una) para apagar el sistema.
echo ============================================================================
endlocal
