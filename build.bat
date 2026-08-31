@echo off
REM ============================================================================
REM  build.bat  -  Genera el ejecutable empaquetado del sistema web (frontend
REM               compilado + backend + pywebview) con PyInstaller --onedir.
REM               Resultado:  dist\ConfiguradorPlantaWeb\ConfiguradorPlantaWeb.exe
REM               --onedir (no --onefile): arranca en segundos en vez de
REM               re-descomprimir todo en cada arranque (ver PLAN_WEBAPP.md).
REM               Requiere haber corrido install.bat antes.
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

echo === Compilando el frontend (npm run build) ===
pushd "front"
call npm run build
if errorlevel 1 (
  echo [ERROR] Fallo el build del frontend.
  popd
  pause
  exit /b 1
)
popd

echo.
echo === Instalando PyInstaller en el entorno del backend ===
"backend\.venv\Scripts\python.exe" -m pip install --quiet pyinstaller
if errorlevel 1 (
  echo [ERROR] No se pudo instalar PyInstaller.
  pause
  exit /b 1
)

echo.
echo === Compilando el ejecutable (esto puede tardar unos minutos) ===
pushd "backend"
"%~dp0backend\.venv\Scripts\python.exe" -m PyInstaller ^
  --noconfirm --clean ^
  --onedir --windowed ^
  --name "ConfiguradorPlantaWeb" ^
  --paths "." ^
  --collect-submodules uvicorn ^
  --collect-submodules webview ^
  --add-data "app\recetas232.csv;." ^
  --add-data "profiles;profiles" ^
  --add-data "..\front\dist;front_dist" ^
  --distpath "..\dist" ^
  --workpath "build\work" ^
  --specpath "build" ^
  "launcher.py"
set "BUILD_ERR=%ERRORLEVEL%"
popd

if not "%BUILD_ERR%"=="0" (
  echo.
  echo [ERROR] Fallo la compilacion.
  pause
  exit /b 1
)

echo.
echo ============================================================================
echo  LISTO. Ejecutable generado en:
echo     dist\ConfiguradorPlantaWeb\ConfiguradorPlantaWeb.exe
echo.
echo  Copia la carpeta dist\ConfiguradorPlantaWeb\ COMPLETA (no solo el .exe)
echo  a cualquier PC con Windows y hace doble clic en el .exe.
echo  Al iniciar creara, junto al .exe:
echo     - profiles\        (perfiles de maquina; se pueden agregar mas)
echo     - datos\^<id^>\       (original + actual + meta.json por maquina)
echo ============================================================================
pause
endlocal
