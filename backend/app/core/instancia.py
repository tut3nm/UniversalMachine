"""Instancia única por máquina (Nivel 4.4 del plan de mejoras).

Aun con un .exe portable, nada impide que un operario abra dos ventanas de
la app apuntando a la misma máquina en la misma PC — la segunda pisaría
los cambios de la primera sin avisar. Este módulo implementa un lock por
archivo (`datos/<id>/.lock`) con el PID de quien lo tiene, y limpia locks
huérfanos (de un proceso que ya no existe, p. ej. tras un crash) en vez de
dejar la máquina bloqueada para siempre.

No es un lock de red ni resuelve el caso multi-PC — eso queda
explícitamente fuera de alcance (ver PLAN_MEJORAS.md, Nivel 4.4): el
supuesto del proyecto es un operario a la vez por máquina, en una sola PC."""

from __future__ import annotations

import json
import os
import socket
from datetime import datetime

LOCK_FILENAME = ".lock"


class InstanciaBloqueadaError(Exception):
    """Ya hay otra instancia viva usando esta máquina en esta PC."""

    def __init__(self, info: dict):
        self.info = info
        super().__init__(f"Instancia bloqueada por PID {info.get('pid')}")


def _lock_path(data_dir: str) -> str:
    return os.path.join(data_dir, LOCK_FILENAME)


def _proceso_vivo(pid) -> bool:
    """True si `pid` corresponde a un proceso vivo. En Windows (única
    plataforma de despliegue de esta app) se abre un handle de solo
    consulta — NUNCA se usa os.kill(), que en Windows termina el proceso
    en vez de solo consultarlo. Fuera de Windows (por ejemplo corriendo la
    suite en otro SO durante desarrollo) se asume vivo, para no autolimpiar
    un lock a ciegas sin poder verificarlo de verdad."""
    if not isinstance(pid, int) or isinstance(pid, bool) or pid <= 0:
        return False
    try:
        import ctypes
        kernel32 = ctypes.windll.kernel32  # type: ignore[attr-defined]
    except (ImportError, AttributeError):
        return True
    PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
    handle = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
    if not handle:
        return False
    kernel32.CloseHandle(handle)
    return True


def leer_lock(data_dir: str) -> dict | None:
    path = _lock_path(data_dir)
    if not os.path.exists(path):
        return None
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError, UnicodeDecodeError):
        return None


def adquirir(data_dir: str) -> None:
    """Toma el lock de `data_dir`. Lanza InstanciaBloqueadaError si ya hay
    otra instancia viva. Si el lock existente pertenece a un proceso que ya
    no corre (huérfano — típicamente por un crash o un `taskkill`), lo
    limpia y toma el lock sin más trámite."""
    existente = leer_lock(data_dir)
    if existente is not None and _proceso_vivo(existente.get("pid")):
        raise InstanciaBloqueadaError(existente)
    nuevo = {"pid": os.getpid(), "host": socket.gethostname(),
             "timestamp": datetime.now().isoformat(timespec="seconds")}
    with open(_lock_path(data_dir), "w", encoding="utf-8") as f:
        json.dump(nuevo, f)


def liberar(data_dir: str) -> None:
    """Best-effort: si no se puede borrar (permisos, ya no existe), no debe
    impedir que la app cierre igual."""
    try:
        os.remove(_lock_path(data_dir))
    except OSError:
        pass
