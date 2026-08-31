"""
conftest.py — utilidades compartidas de la suite.

Dos fragilidades conocidas y NO relacionadas con el código de la app:

1. ttkbootstrap mantiene un `Style` singleton por PROCESO, atado a la
   primera `tb.Window` (root Tk) que se crea. Instanciar una segunda
   ventana completa de la App real en el mismo proceso de pytest — aunque
   la primera ya se haya destruido — puede romper la creación de widgets
   nuevos en la segunda. `pytest-forked` sería la solución estándar (aislar
   cada test en su propio proceso), pero usa os.fork(), que no existe en
   Windows. La alternativa acá es `ejecutar_test_en_subproceso_aislado()`:
   cada test que instancia la App real se relanza a sí mismo como un
   proceso de `python -m pytest` nuevo la primera vez que se ejecuta.

2. Independientemente de lo anterior, en esta máquina se observó que crear
   un root de Tkinter falla de forma intermitente incluso en un proceso
   Python recién iniciado, con errores de Tcl del estilo "couldn't read
   file ...listbox.tcl: no such file or directory". Es un problema externo
   del entorno (muy probablemente sincronización en la nube de la carpeta
   de instalación de Python bajo AppData, o interferencia de un antivirus
   al escanear los .exe de Python que se lanzan) — se confirmó reproduciendo
   `tkinter.Tk()` suelto, sin ninguna app ni test de por medio, y fallando
   de forma no determinística. `ejecutar_test_en_subproceso_aislado()`
   reintenta una vez ante esta firma de error específica antes de darse
   por vencido, para no ensuciar la suite con un fallo que no tiene nada
   que ver con el código.
"""

import os
import re
import subprocess
import sys

_resultado_cache: bool | None = None

_MARCADOR_SUBPROCESO = "_GUI_TEST_SUBPROCESS"

# Firma específica del fallo ambiental conocido (punto 2 de arriba). Solo se
# reintenta ante ESTE error puntual — cualquier otro fallo (una assertion
# real, un traceback de la app) se reporta tal cual, sin reintentar, para no
# esconder jamás un bug real detrás de un reintento.
_PATRON_FALLO_AMBIENTAL = re.compile(
    r"couldn't read file .*\.tcl|Can't find a usable tk\.tcl|"
    r"invalid command name \"tcl_findLibrary\"")


def tk_disponible() -> bool:
    """Prueba UNA sola vez por proceso si hay soporte de Tkinter real (crea
    y destruye un root de prueba)."""
    global _resultado_cache
    if _resultado_cache is not None:
        return _resultado_cache
    try:
        import tkinter as tk
    except ImportError:
        _resultado_cache = False
        return False
    try:
        root = tk.Tk()
        root.destroy()
        _resultado_cache = True
    except tk.TclError:
        _resultado_cache = False
    return _resultado_cache


def en_subproceso_aislado() -> bool:
    """True si el proceso actual YA es el subproceso relanzado (no hay que
    volver a relanzar de nuevo)."""
    return os.environ.get(_MARCADOR_SUBPROCESO) == "1"


def _correr_subproceso(nodeid: str, root: str, env: dict):
    return subprocess.run(
        [sys.executable, "-m", "pytest", nodeid, "-q", "-p", "no:cacheprovider"],
        cwd=root, env=env, capture_output=True, text=True, timeout=120)


def ejecutar_test_en_subproceso_aislado(nodeid: str) -> None:
    """Relanza `nodeid` (p. ej. 'tests/test_app_backups.py::test_x') como un
    proceso de `python -m pytest` completamente nuevo, y hace fallar el test
    actual (con el stdout/stderr del subproceso) si ese proceso no termina
    con éxito. Reintenta UNA vez, solo si el fallo coincide con la firma del
    problema ambiental conocido (ver docstring del módulo).

    El llamador debe comprobar `en_subproceso_aislado()` ANTES de llamar a
    esto — si ya estamos dentro del subproceso, no hay que relanzar de
    nuevo (sería recursión infinita)."""
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    env = dict(os.environ)
    env[_MARCADOR_SUBPROCESO] = "1"

    resultado = _correr_subproceso(nodeid, root, env)
    if resultado.returncode != 0 and _PATRON_FALLO_AMBIENTAL.search(resultado.stdout or ""):
        resultado = _correr_subproceso(nodeid, root, env)  # un solo reintento

    if resultado.returncode != 0:
        raise AssertionError(
            f"Falló en el subproceso aislado (código {resultado.returncode}):\n"
            f"--- stdout ---\n{resultado.stdout}\n--- stderr ---\n{resultado.stderr}")
