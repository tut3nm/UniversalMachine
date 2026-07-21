@echo off
REM ============================================================================
REM  build.bat  -  Genera el ejecutable PORTABLE (.exe) con PyInstaller.
REM                Resultado:  dist\ConfiguradorMaquina232.exe
REM                Ese unico archivo se copia a cualquier PC con Windows.
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

echo === Instalando dependencias (PyInstaller + ttkbootstrap + openpyxl) ===
%PYEXE% -m pip install --upgrade pip
%PYEXE% -m pip install pyinstaller ttkbootstrap openpyxl
if errorlevel 1 (
  echo [ERROR] No se pudieron instalar las dependencias.
  pause
  exit /b 1
)

echo.
echo === Compilando ejecutable portable ===
%PYEXE% -m PyInstaller ^
  --noconfirm --clean ^
  --onefile --windowed ^
  --name "ConfiguradorPlanta" ^
  --collect-submodules ttkbootstrap ^
  --add-data "%~dp0recetas232.csv;." ^
  --add-data "%~dp0profiles;profiles" ^
  --distpath "dist" ^
  --workpath "build\work" ^
  --specpath "build" ^
  "src\app.py"

if errorlevel 1 (
  echo.
  echo [ERROR] Fallo la compilacion.
  pause
  exit /b 1
)

echo.
echo ============================================================================
echo  LISTO. Ejecutable portable generado en:
echo     dist\ConfiguradorPlanta.exe
echo.
echo  Copia ese .exe a cualquier PC con Windows y hace doble clic.
echo  Al iniciar creara, junto al .exe:
echo     - profiles\        (perfiles de maquina; se pueden agregar mas)
echo     - datos\^<id^>\       (original + actual + meta.json por maquina)
echo ============================================================================
pause
endlocal
