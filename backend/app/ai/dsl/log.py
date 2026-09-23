"""
Log liviano de ejecuciones del asistente (PLAN_ASISTENTE_IA.md, decision 9 de
la seccion 2): un .jsonl append-only con fecha, quien, que pidio, y el
PROGRAMA DSL que se ejecuto. No guarda el archivo de salida (eso ya vive en
docs/Recetas/ o en el .zip descargado): guardar las 3-6 operaciones del
programa alcanza para reconstruir de donde salio una receta, y cuesta lo
mismo que loguear solo "se genero un .zip" (mismo patron append-only que
app/core/historial.py, pero sin su semantica de alta/modificacion/baja por
registro, que no aplica aca).
"""
from __future__ import annotations

import getpass
import json
import os
from datetime import datetime

import paths


def _path_log() -> str:
    d = os.path.join(paths.app_base_dir(), "datos", "log")
    os.makedirs(d, exist_ok=True)
    return os.path.join(d, "asistente.jsonl")


def _usuario_actual() -> str:
    try:
        return getpass.getuser()
    except OSError:
        return "desconocido"


def registrar_ejecucion(
    operacion: str, programa: list[dict], cantidad_archivos: int, texto_usuario: str = ""
) -> None:
    evento = {
        "timestamp": datetime.now().isoformat(timespec="seconds"),
        "usuario": _usuario_actual(),
        "operacion": operacion,
        "texto_usuario": texto_usuario,
        "programa": programa,
        "cantidad_archivos": cantidad_archivos,
    }
    with open(_path_log(), "a", encoding="utf-8", newline="") as f:
        f.write(json.dumps(evento, ensure_ascii=False) + "\n")
        f.flush()
        os.fsync(f.fileno())


def leer_eventos() -> list[dict]:
    """Todos los eventos, mas viejo primero. Una linea corrupta se ignora
    (mismo criterio que historial.leer_eventos): el log es informativo, no
    debe volverse inconsultable por una sola linea danada."""
    path = _path_log()
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
