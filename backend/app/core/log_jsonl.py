"""
Log liviano append-only en formato .jsonl, un archivo por 'origen' dentro de
datos/log/. Mismo patron que historial.py (un objeto JSON por linea, con
flush+fsync) pero sin su semantica fija de alta/modificacion/baja por
registro, que no aplica a operaciones puntuales como las del asistente de
IA o el editor de recetas matriz: ahi alcanza con fecha + usuario + los
campos propios de esa operacion, elegidos por quien llama a registrar().
"""
from __future__ import annotations

import getpass
import json
import os
from datetime import datetime

import paths


def _path(origen: str) -> str:
    d = os.path.join(paths.app_base_dir(), "datos", "log")
    os.makedirs(d, exist_ok=True)
    return os.path.join(d, f"{origen}.jsonl")


def _usuario_actual() -> str:
    try:
        return getpass.getuser()
    except OSError:
        return "desconocido"


def registrar(origen: str, campos: dict) -> None:
    evento = {
        "timestamp": datetime.now().isoformat(timespec="seconds"),
        "usuario": _usuario_actual(),
        **campos,
    }
    with open(_path(origen), "a", encoding="utf-8", newline="") as f:
        f.write(json.dumps(evento, ensure_ascii=False) + "\n")
        f.flush()
        os.fsync(f.fileno())


def leer_eventos(origen: str) -> list[dict]:
    """Todos los eventos de ese origen, mas viejo primero. Una linea
    corrupta se ignora: el log es informativo, no debe volverse
    inconsultable por una sola linea danada (ej. un corte de luz a mitad de
    un append)."""
    path = _path(origen)
    if not os.path.exists(path):
        return []
    eventos = []
    with open(path, encoding="utf-8") as f:
        for linea in f:
            linea = linea.strip()
            if not linea:
                continue
            try:
                eventos.append(json.loads(linea))
            except json.JSONDecodeError:
                continue
    return eventos
