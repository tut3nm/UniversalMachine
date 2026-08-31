"""
backups.py
==========
Respaldos rotativos de actual.<ext>, en datos/<id>/backups/.

Política de retención (Nivel 2.1 del plan de mejoras):
  - todos los backups de HOY
  - uno por día de los últimos 30 días (el más reciente de cada día)
  - uno por mes del último año (el más reciente de cada mes)
  - nada más viejo que eso se purga

Cada backup se escribe de forma atómica (ver io_seguro.py) junto con un
sidecar .sha256 para poder verificar integridad antes de restaurar — un
backup no sirve de nada si no se puede confiar en que es exactamente lo que
se escribió en su momento.
"""

from __future__ import annotations

import hashlib
import os
import re
from dataclasses import dataclass
from datetime import datetime, timedelta

from io_seguro import escribir_atomico, escribir_bytes_atomico

_NOMBRE_RE = re.compile(r"^actual-(\d{8}-\d{6}-\d{6})\.")


@dataclass
class BackupInfo:
    nombre: str
    ruta: str
    timestamp: datetime
    tamano_bytes: int

    @property
    def ruta_hash(self) -> str:
        return f"{self.ruta}.sha256"


def _carpeta_backups(data_dir: str) -> str:
    d = os.path.join(data_dir, "backups")
    os.makedirs(d, exist_ok=True)
    return d


def crear_backup(data_dir: str, path_actual: str, ext: str) -> str | None:
    """Copia el actual.<ext> VIGENTE (el que está a punto de sobreescribirse)
    a backups/actual-<timestamp>.<ext>, con su hash sha256 al lado. Se debe
    llamar ANTES de escribir el nuevo estado. Devuelve la ruta del backup
    creado, o None si no había nada que respaldar todavía (primera vez que
    se guarda una máquina recién creada, sin historia previa)."""
    if not os.path.exists(path_actual):
        return None
    with open(path_actual, "rb") as f:
        contenido = f.read()
    carpeta = _carpeta_backups(data_dir)
    # Microsegundos en el nombre: varias ediciones seguidas dentro del mismo
    # segundo (frecuente en uso real) no deben pisarse el archivo de backup.
    ts = datetime.now().strftime("%Y%m%d-%H%M%S-%f")
    destino = os.path.join(carpeta, f"actual-{ts}.{ext}")
    escribir_bytes_atomico(destino, contenido)
    hash_hex = hashlib.sha256(contenido).hexdigest()
    escribir_atomico(f"{destino}.sha256", hash_hex, encoding="utf-8")
    return destino


def listar_backups(data_dir: str) -> list[BackupInfo]:
    """Todos los backups existentes, más nuevo primero."""
    carpeta = _carpeta_backups(data_dir)
    out: list[BackupInfo] = []
    for nombre in os.listdir(carpeta):
        if nombre.endswith(".sha256"):
            continue
        m = _NOMBRE_RE.match(nombre)
        if not m:
            continue
        try:
            ts = datetime.strptime(m.group(1), "%Y%m%d-%H%M%S-%f")
        except ValueError:
            continue
        ruta = os.path.join(carpeta, nombre)
        try:
            tamano = os.path.getsize(ruta)
        except OSError:
            continue
        out.append(BackupInfo(nombre=nombre, ruta=ruta, timestamp=ts,
                              tamano_bytes=tamano))
    out.sort(key=lambda b: b.timestamp, reverse=True)
    return out


def verificar_integridad(backup: BackupInfo) -> bool:
    """True si el contenido del backup coincide con el hash guardado junto
    a él. False si el hash no coincide O si falta el sidecar .sha256 (un
    backup sin hash no se puede dar por confiable)."""
    if not os.path.exists(backup.ruta_hash):
        return False
    try:
        with open(backup.ruta_hash, encoding="utf-8") as f:
            esperado = f.read().strip()
        with open(backup.ruta, "rb") as f:
            real = hashlib.sha256(f.read()).hexdigest()
    except OSError:
        return False
    return real == esperado


def restaurar_backup(backup: BackupInfo, path_actual: str) -> None:
    """Sobrescribe path_actual con el contenido del backup, de forma
    atómica. No verifica integridad acá — el llamador debe llamar
    verificar_integridad() antes y decidir si de todos modos quiere
    continuar (ver BackupsDialog en app.py)."""
    with open(backup.ruta, "rb") as f:
        contenido = f.read()
    escribir_bytes_atomico(path_actual, contenido)


def purgar_backups(data_dir: str, ahora: datetime | None = None) -> int:
    """Aplica la política de retención y borra los backups que sobran.
    Devuelve la cantidad de backups eliminados."""
    ahora = ahora or datetime.now()
    backups = listar_backups(data_dir)  # más nuevo primero
    if not backups:
        return 0

    hoy = ahora.date()
    mantener: set[str] = set()
    por_dia: dict = {}
    por_mes: dict = {}

    for b in backups:
        if b.timestamp.date() == hoy:
            mantener.add(b.nombre)
            continue
        edad_dias = (ahora - b.timestamp).days
        if edad_dias <= 30:
            clave_dia = b.timestamp.date()
            por_dia.setdefault(clave_dia, b.nombre)  # el primero visto es el más nuevo de ese día
        if edad_dias <= 365:
            clave_mes = (b.timestamp.year, b.timestamp.month)
            por_mes.setdefault(clave_mes, b.nombre)

    mantener |= set(por_dia.values())
    mantener |= set(por_mes.values())

    eliminados = 0
    for b in backups:
        if b.nombre in mantener:
            continue
        try:
            os.remove(b.ruta)
        except OSError:
            continue
        try:
            os.remove(b.ruta_hash)
        except OSError:
            pass
        eliminados += 1
    return eliminados


# -- Comparación entre el estado actual y un backup (para la vista previa) ---

def resumir_diferencias(store_actual, store_backup) -> dict:
    """Compara store_actual (el estado vigente) contra store_backup (lo que
    quedaría si se restaura ese backup). Se nombra en términos de lo que
    pasaría SI se restaura: qué se perdería, qué se recuperaría, y qué
    cambiaría. `store_actual` y `store_backup` son DataStore con el mismo
    perfil (misma clave)."""
    clave = store_actual.profile.campo_clave().nombre_interno
    idx_actual = {r[clave]: r for r in store_actual.records}
    idx_backup = {r[clave]: r for r in store_backup.records}

    se_perderian = sorted(k for k in idx_actual if k not in idx_backup)
    se_recuperarian = sorted(k for k in idx_backup if k not in idx_actual)
    cambiarian = sorted(k for k in idx_actual
                        if k in idx_backup and idx_actual[k] != idx_backup[k])
    return {
        "se_perderian": se_perderian,
        "se_recuperarian": se_recuperarian,
        "cambiarian": cambiarian,
    }
