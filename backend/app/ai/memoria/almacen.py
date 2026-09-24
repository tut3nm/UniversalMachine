"""
Persistencia de formatos guardados: SQLite en la carpeta de datos del
backend, compartida por todos los usuarios (PLAN_MEMORIA_FORMATOS.md,
secciones 2 y 7). Una tabla `formatos`; huella y regla como JSON. Cada
escritura es su propia conexion/transaccion (mismo nivel de concurrencia que
sqlite3 por default: alcanza para el uso de un operario a la vez por PC).
"""
from __future__ import annotations

import contextlib
import json
import os
import sqlite3
import uuid
from dataclasses import dataclass
from datetime import datetime

from app import _bootstrap  # noqa: F401  (side effect: agrega app/core/ a sys.path)

import paths

_ESQUEMA = """
CREATE TABLE IF NOT EXISTS formatos (
    id TEXT PRIMARY KEY,
    pantalla TEXT NOT NULL,
    nombre TEXT NOT NULL,
    huella TEXT NOT NULL,
    regla TEXT NOT NULL,
    explicacion TEXT NOT NULL,
    creado_por TEXT NOT NULL,
    creado TEXT NOT NULL,
    usos INTEGER NOT NULL DEFAULT 0,
    ultimo_uso TEXT
)
"""


@dataclass(frozen=True)
class Formato:
    id: str
    pantalla: str
    nombre: str
    huella: dict
    regla: dict
    explicacion: str
    creado_por: str
    creado: str
    usos: int = 0
    ultimo_uso: str | None = None


def _db_path() -> str:
    d = os.path.join(paths.app_base_dir(), "datos", "memoria")
    os.makedirs(d, exist_ok=True)
    return os.path.join(d, "formatos.db")


@contextlib.contextmanager
def _conn():
    conn = sqlite3.connect(_db_path())
    try:
        conn.execute(_ESQUEMA)
        yield conn
        conn.commit()
    finally:
        conn.close()


_COLUMNAS = (
    "id", "pantalla", "nombre", "huella", "regla", "explicacion",
    "creado_por", "creado", "usos", "ultimo_uso",
)


def _fila_a_formato(fila: tuple) -> Formato:
    d = dict(zip(_COLUMNAS, fila))
    return Formato(
        id=d["id"], pantalla=d["pantalla"], nombre=d["nombre"],
        huella=json.loads(d["huella"]), regla=json.loads(d["regla"]),
        explicacion=d["explicacion"], creado_por=d["creado_por"], creado=d["creado"],
        usos=d["usos"], ultimo_uso=d["ultimo_uso"],
    )


def listar(pantalla: str | None = None) -> list[Formato]:
    with _conn() as conn:
        if pantalla is not None:
            filas = conn.execute(
                "SELECT * FROM formatos WHERE pantalla = ? ORDER BY creado DESC", (pantalla,)
            ).fetchall()
        else:
            filas = conn.execute("SELECT * FROM formatos ORDER BY creado DESC").fetchall()
    return [_fila_a_formato(f) for f in filas]


def obtener(id_: str) -> Formato | None:
    with _conn() as conn:
        fila = conn.execute("SELECT * FROM formatos WHERE id = ?", (id_,)).fetchone()
    return _fila_a_formato(fila) if fila else None


def guardar(
    pantalla: str, nombre: str, huella: dict, regla: dict, explicacion: str, creado_por: str
) -> Formato:
    id_ = str(uuid.uuid4())
    ahora = datetime.now().isoformat(timespec="seconds")
    with _conn() as conn:
        conn.execute(
            "INSERT INTO formatos "
            "(id, pantalla, nombre, huella, regla, explicacion, creado_por, creado, usos, ultimo_uso) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, 0, NULL)",
            (
                id_, pantalla, nombre, json.dumps(huella, ensure_ascii=False),
                json.dumps(regla, ensure_ascii=False), explicacion, creado_por, ahora,
            ),
        )
    return Formato(id_, pantalla, nombre, huella, regla, explicacion, creado_por, ahora)


def actualizar(
    id_: str,
    nombre: str | None = None,
    huella: dict | None = None,
    regla: dict | None = None,
    explicacion: str | None = None,
) -> Formato:
    """Guarda la version anterior no hace falta pisarla en el momento (queda
    en el log de ejecuciones que llevo a esta actualizacion); volver atras
    con esa base es tarea de la pantalla de administracion (fase 4)."""
    existente = obtener(id_)
    if existente is None:
        raise ValueError(f"No existe el formato '{id_}'.")
    nuevo = Formato(
        id=existente.id, pantalla=existente.pantalla,
        nombre=nombre if nombre is not None else existente.nombre,
        huella=huella if huella is not None else existente.huella,
        regla=regla if regla is not None else existente.regla,
        explicacion=explicacion if explicacion is not None else existente.explicacion,
        creado_por=existente.creado_por, creado=existente.creado,
        usos=existente.usos, ultimo_uso=existente.ultimo_uso,
    )
    with _conn() as conn:
        conn.execute(
            "UPDATE formatos SET nombre = ?, huella = ?, regla = ?, explicacion = ? WHERE id = ?",
            (
                nuevo.nombre, json.dumps(nuevo.huella, ensure_ascii=False),
                json.dumps(nuevo.regla, ensure_ascii=False), nuevo.explicacion, id_,
            ),
        )
    return nuevo


def registrar_uso(id_: str) -> None:
    ahora = datetime.now().isoformat(timespec="seconds")
    with _conn() as conn:
        conn.execute("UPDATE formatos SET usos = usos + 1, ultimo_uso = ? WHERE id = ?", (ahora, id_))


def borrar(id_: str) -> None:
    with _conn() as conn:
        conn.execute("DELETE FROM formatos WHERE id = ?", (id_,))
