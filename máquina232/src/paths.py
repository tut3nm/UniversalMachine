"""
paths.py
========
Ubicación de recursos (perfiles, archivos de datos) tanto en desarrollo como
en el ejecutable empaquetado con PyInstaller.

Estructura junto al ejecutable / raíz del proyecto:
    profiles/               <- perfiles JSON (bundleados + los que cree el usuario)
    datos/<id_maquina>/     <- original.<ext>, actual.<ext>, meta.json por máquina
"""

from __future__ import annotations

import os
import shutil
import sys


def resource_path(rel: str) -> str:
    """Ruta a un recurso embebido (funciona con PyInstaller y en desarrollo)."""
    base = getattr(sys, "_MEIPASS", None)
    if base:
        return os.path.join(base, rel)
    here = os.path.dirname(os.path.abspath(__file__))
    for c in (os.path.join(here, rel), os.path.join(here, "..", rel)):
        if os.path.exists(c):
            return os.path.abspath(c)
    return os.path.abspath(os.path.join(here, "..", rel))


def app_base_dir() -> str:
    """Carpeta escribible: junto al .exe (empaquetado) o raíz del proyecto."""
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    return os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))


def profiles_dir() -> str:
    """Carpeta escribible de perfiles, sembrada desde los perfiles embebidos.

    Los perfiles de fábrica vienen embebidos (solo lectura); al primer arranque
    se copian a una carpeta escribible junto al ejecutable, para que el
    asistente de alta pueda agregar perfiles nuevos ahí."""
    dest = os.path.join(app_base_dir(), "profiles")
    os.makedirs(dest, exist_ok=True)
    bundled = resource_path("profiles")
    if os.path.isdir(bundled) and os.path.abspath(bundled) != os.path.abspath(dest):
        for name in os.listdir(bundled):
            if name.endswith(".json"):
                target = os.path.join(dest, name)
                if not os.path.exists(target):
                    shutil.copyfile(os.path.join(bundled, name), target)
    return dest


def data_dir_for(profile_id: str) -> str:
    d = os.path.join(app_base_dir(), "datos", str(profile_id))
    os.makedirs(d, exist_ok=True)
    return d
