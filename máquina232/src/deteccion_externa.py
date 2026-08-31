"""Detección de modificación externa (Nivel 4.3 del plan de mejoras).

Aun con un .exe por PC, `actual.<ext>` puede ser tocado por fuera de la
app (alguien lo copia a mano, un script, la propia máquina leyendo/
reescribiendo el archivo). Este módulo guarda el hash del archivo al
cargarlo/guardarlo y permite verificar, justo antes del siguiente guardado,
si cambió por fuera — sin eso, un guardado de la app pisaría en silencio
un cambio externo."""

from __future__ import annotations

import hashlib
import os


def hash_archivo(path: str) -> str | None:
    """SHA-256 del archivo, o None si no existe (todavía no se guardó
    nunca, o fue borrado por fuera — eso también es una forma válida de
    "cambió", que el llamador debe tratar como tal)."""
    if not os.path.exists(path):
        return None
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def fue_modificado_externamente(path: str, hash_conocido: str | None) -> bool:
    """True si el contenido de `path` en disco ya no coincide con
    `hash_conocido` (el hash que la app vio la última vez que leyó o
    escribió ese archivo). Si `hash_conocido` es None (primera vez, sin
    referencia previa), no hay nada contra qué comparar: no se reporta
    modificación."""
    if hash_conocido is None:
        return False
    return hash_archivo(path) != hash_conocido
