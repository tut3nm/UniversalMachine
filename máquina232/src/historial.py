"""
historial.py
============
Registro append-only de cambios (datos/<id>/historial.jsonl), un objeto
JSON por línea. Cada entrada: timestamp, usuario del sistema operativo,
tipo de acción, clave del registro afectado, valores anteriores/nuevos, y
origen (manual, un archivo Excel importado, una restauración, etc.).

IMPORTANTE — esto NO es un log de auditoría a prueba de manipulación: el
archivo es un .jsonl de texto plano, editable por cualquiera con acceso a la
carpeta de datos. Sirve para trazabilidad ("qué cambió y cuándo, y quién
estaba loggeado en Windows en ese momento") y para poder investigar o
revertir un cambio pasado — no para cumplir un requisito legal de
integridad de auditoría. Si la empresa necesita eso, hace falta un sistema
de firma/hash encadenado, que queda fuera del alcance de este nivel.
"""

from __future__ import annotations

import getpass
import gzip
import json
import os
import shutil
from dataclasses import dataclass
from datetime import datetime, timedelta

RETENCION_DIAS = 365
TAMANO_MAX_BYTES = 50 * 1024 * 1024  # 50 MB dispara rotación por tamaño

ACCIONES_VALIDAS = {"alta", "modificacion", "baja", "importacion", "restauracion", "limpieza"}


@dataclass
class EventoHistorial:
    timestamp: str
    usuario: str
    accion: str
    clave: str
    anteriores: dict | None
    nuevos: dict | None
    origen: str
    version: str | None = None

    def to_dict(self) -> dict:
        return {
            "timestamp": self.timestamp, "usuario": self.usuario,
            "accion": self.accion, "clave": self.clave,
            "anteriores": self.anteriores, "nuevos": self.nuevos,
            "origen": self.origen, "version": self.version,
        }


def _usuario_actual() -> str:
    try:
        return getpass.getuser()
    except OSError:
        return "desconocido"


def registrar(path_historial: str, accion: str, clave: str,
              anteriores: dict | None = None, nuevos: dict | None = None,
              origen: str = "manual", version: str | None = None) -> None:
    """Agrega una línea al historial. Es un append: no reescribe el archivo
    entero (a diferencia de io_seguro.escribir_atomico, pensado para
    archivos que se regeneran completos cada vez). El flush+fsync reduce
    (no elimina del todo, en discos de red no hay garantía absoluta) el
    riesgo de perder la línea si el proceso se corta justo después.

    `version` es la versión de la app que generó el evento (Nivel 3.4): si
    aparece un dato raro en el historial, permite saber qué build lo
    produjo. Puede quedar en None para eventos donde no aplica/no se sabe."""
    if accion not in ACCIONES_VALIDAS:
        raise ValueError(f"acción de historial desconocida: {accion!r}")
    evento = EventoHistorial(
        timestamp=datetime.now().isoformat(timespec="seconds"),
        usuario=_usuario_actual(), accion=accion, clave=str(clave),
        anteriores=anteriores, nuevos=nuevos, origen=origen, version=version)
    carpeta = os.path.dirname(path_historial)
    if carpeta:
        os.makedirs(carpeta, exist_ok=True)
    with open(path_historial, "a", encoding="utf-8", newline="") as f:
        f.write(json.dumps(evento.to_dict(), ensure_ascii=False) + "\n")
        f.flush()
        os.fsync(f.fileno())


def leer_eventos(path_historial: str) -> list[dict]:
    """Todos los eventos, en el orden en que se registraron (más viejo
    primero). Una línea corrupta se ignora en vez de abortar toda la
    lectura — el historial es informativo, no debe volverse inconsultable
    por una sola línea dañada (p. ej. por un corte de luz a mitad de un
    append)."""
    if not os.path.exists(path_historial):
        return []
    eventos = []
    with open(path_historial, encoding="utf-8") as f:
        for linea in f:
            linea = linea.strip()
            if not linea:
                continue
            try:
                eventos.append(json.loads(linea))
            except json.JSONDecodeError:
                continue
    return eventos


def rotar_si_hace_falta(path_historial: str, ahora: datetime | None = None) -> str | None:
    """Si el historial activo superó TAMANO_MAX_BYTES, archiva TODO su
    contenido a un .jsonl.gz aparte y lo deja vacío. Devuelve la ruta del
    archivo comprimido, o None si no hizo falta."""
    if not os.path.exists(path_historial):
        return None
    if os.path.getsize(path_historial) < TAMANO_MAX_BYTES:
        return None
    ahora = ahora or datetime.now()
    destino = f"{path_historial}.{ahora:%Y%m%d-%H%M%S}.gz"
    with open(path_historial, "rb") as f_in, gzip.open(destino, "wb") as f_out:
        shutil.copyfileobj(f_in, f_out)
    with open(path_historial, "w", encoding="utf-8"):
        pass  # vaciar el archivo activo, mismo path
    return destino


def purgar_eventos_viejos(path_historial: str, dias: int = RETENCION_DIAS,
                          ahora: datetime | None = None) -> int:
    """Archiva (comprime, NO borra el contenido) los eventos más viejos que
    `dias` a un .jsonl.gz aparte, dejando en el historial activo solo lo
    reciente. Devuelve la cantidad de eventos archivados."""
    ahora = ahora or datetime.now()
    eventos = leer_eventos(path_historial)
    if not eventos:
        return 0

    limite = ahora - timedelta(days=dias)
    recientes, viejos = [], []
    for e in eventos:
        try:
            ts = datetime.fromisoformat(e["timestamp"])
        except (KeyError, ValueError, TypeError):
            recientes.append(e)  # timestamp ilegible: no se descarta a ciegas
            continue
        (viejos if ts < limite else recientes).append(e)

    if not viejos:
        return 0

    destino = f"{path_historial}.archivado-{ahora:%Y%m%d-%H%M%S}.gz"
    with gzip.open(destino, "wt", encoding="utf-8") as f:
        for e in viejos:
            f.write(json.dumps(e, ensure_ascii=False) + "\n")
    with open(path_historial, "w", encoding="utf-8", newline="") as f:
        for e in recientes:
            f.write(json.dumps(e, ensure_ascii=False) + "\n")
    return len(viejos)
