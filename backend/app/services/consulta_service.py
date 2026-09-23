"""Endpoints de sólo lectura (+ restaurar backup) para Backups, Historial y
Diferencias contra el original — Fase 1 del plan expone lectura; el resto
de las acciones de estos diálogos (deshacer/rehacer, exportar CSV desde la
UI, etc.) quedan para Fase 2, ver PLAN_WEBAPP.md."""

from __future__ import annotations

import dataclasses
import os
from datetime import datetime, timedelta
from typing import Any

from app import _bootstrap  # noqa: F401

import backups as backups_mod
import deteccion_externa
import diferencias as diferencias_mod
import historial as historial_mod
import informe as informe_mod
import io_seguro
import paths
from datastore import DataStore

from app.services.maquinas_service import (  # reutiliza la resolución de rutas/perfil
    MaquinaNoEncontrada,
    _cargar_store,
    _CACHE_LECTURA,
    _rutas,
    cargar_perfil,
    limpiar_pilas_deshacer,
)


def _asdict_backup(b) -> dict[str, Any]:
    d = dataclasses.asdict(b)
    d["timestamp"] = b.timestamp.isoformat()
    d["ruta_hash"] = b.ruta_hash
    d["integridad_ok"] = backups_mod.verificar_integridad(b)
    return d


def listar_backups(machine_id: str) -> list[dict[str, Any]]:
    profile = cargar_perfil(machine_id)
    data_dir = paths.data_dir_for(profile.id)
    return [_asdict_backup(b) for b in backups_mod.listar_backups(data_dir)]


def _buscar_backup(data_dir: str, nombre_backup: str):
    candidatos = [b for b in backups_mod.listar_backups(data_dir) if b.nombre == nombre_backup]
    if not candidatos:
        raise FileNotFoundError(f"No existe el backup '{nombre_backup}'")
    return candidatos[0]


def backup_preview(machine_id: str, nombre_backup: str) -> dict[str, Any]:
    """Resumen de impacto de restaurar `nombre_backup`, igual al que muestra
    `BackupsDialog` del escritorio antes de pedir confirmación:
    cuántos registros se perderían, se
    recuperarían o cambiarían de valor, más si el hash del backup verifica."""
    profile = cargar_perfil(machine_id)
    data_dir = paths.data_dir_for(profile.id)
    backup = _buscar_backup(data_dir, nombre_backup)
    store_actual = _cargar_store(profile)
    store_backup = DataStore.load(backup.ruta, profile)
    resumen = backups_mod.resumir_diferencias(store_actual, store_backup)
    resumen["integridad_ok"] = backups_mod.verificar_integridad(backup)
    return resumen


def restaurar_backup(machine_id: str, nombre_backup: str) -> dict[str, Any]:
    profile = cargar_perfil(machine_id)
    data_dir = paths.data_dir_for(profile.id)
    backup = _buscar_backup(data_dir, nombre_backup)
    # La integridad ya se mostró (y, si falló, se advirtió) en el preview; el
    # escritorio no bloquea la restauración por un hash no verificado, solo
    # avisa (app.py:2044) y deja decidir al operario.
    actual, _, _ = _rutas(profile)
    backups_mod.crear_backup(data_dir, actual, profile.extension)  # respalda el estado actual también
    backups_mod.restaurar_backup(backup, actual)
    _CACHE_LECTURA.pop(actual, None)
    limpiar_pilas_deshacer(machine_id)
    historial_mod.registrar(
        os.path.join(data_dir, "historial.jsonl"), accion="restauracion",
        clave=nombre_backup, origen="webapp",
    )
    return {"hash": deteccion_externa.hash_archivo(actual)}


def restaurar_original(machine_id: str) -> dict[str, Any]:
    """Descarta todos los cambios y vuelve al archivo `original.<ext>` tal
    como se cargó la primera vez — el equivalente de "Restaurar" del
    escritorio (⟲, outline-danger en la toolbar)."""
    profile = cargar_perfil(machine_id)
    data_dir = paths.data_dir_for(profile.id)
    actual, original_path, _ = _rutas(profile)
    if not os.path.exists(original_path):
        raise FileNotFoundError("No existe el archivo original de esta máquina.")
    backups_mod.crear_backup(data_dir, actual, profile.extension)
    io_seguro.copiar_atomico(original_path, actual)
    _CACHE_LECTURA.pop(actual, None)
    limpiar_pilas_deshacer(machine_id)
    historial_mod.registrar(
        os.path.join(data_dir, "historial.jsonl"), accion="restauracion",
        clave="original", origen="webapp",
    )
    return {"hash": deteccion_externa.hash_archivo(actual)}


def _eventos_filtrados(machine_id: str, codigo: str | None = None,
                       accion: str | None = None, desde_dias: int | None = None) -> list[dict]:
    """Mismo criterio que `HistorialDialog._eventos_filtrados` del
    escritorio (app.py:2214): substring sin distinguir mayúsculas en el
    código, acción exacta, y antigüedad en días. Más nuevo primero."""
    profile = cargar_perfil(machine_id)
    data_dir = paths.data_dir_for(profile.id)
    eventos = historial_mod.leer_eventos(os.path.join(data_dir, "historial.jsonl"))
    eventos = eventos[::-1]
    if codigo:
        q = codigo.strip().lower()
        eventos = [e for e in eventos if q in str(e.get("clave", "")).lower()]
    if accion:
        eventos = [e for e in eventos if e.get("accion") == accion]
    if desde_dias:
        limite = datetime.now() - timedelta(days=desde_dias)
        def _es_reciente(e: dict) -> bool:
            try:
                return datetime.fromisoformat(e["timestamp"]) >= limite
            except (KeyError, ValueError, TypeError):
                return True
        eventos = [e for e in eventos if _es_reciente(e)]
    return eventos


def listar_historial(machine_id: str, limite: int = 200, codigo: str | None = None,
                     accion: str | None = None, desde_dias: int | None = None) -> list[dict[str, Any]]:
    eventos = _eventos_filtrados(machine_id, codigo, accion, desde_dias)
    return eventos[:limite]


def historial_informe_filas(machine_id: str, codigo: str | None = None,
                            accion: str | None = None, desde_dias: int | None = None) -> list[list[str]]:
    """Filas listas para csv.writer con TODOS los eventos que matchean el
    filtro (sin el tope de `limite` de la vista) — el escritorio exporta lo
    que está mostrado en la tabla, y la tabla del diálogo no pagina
    (app.py:2196)."""
    eventos = _eventos_filtrados(machine_id, codigo, accion, desde_dias)
    return informe_mod.a_filas_csv(eventos)


def diferencias_con_original(machine_id: str) -> dict[str, Any]:
    profile = cargar_perfil(machine_id)
    store_actual = _cargar_store(profile)
    _, original_path, _ = _rutas(profile)
    if not os.path.exists(original_path):
        return {"diffs": []}
    store_original = DataStore.load(original_path, profile)
    diffs = diferencias_mod.comparar_con_original(store_actual, store_original)
    return {"diffs": diffs}


def diferencias_informe_filas(machine_id: str, tipos: set[str] | None = None) -> list[list[str]]:
    """Filas listas para csv.writer con los diffs, opcionalmente filtrados
    por tipo — el escritorio exporta solo lo que quedó visible tras los
    checkboxes de Alta/Baja/Modificación (`DiffsDialog._exportar`,
    app.py:2406)."""
    profile = cargar_perfil(machine_id)
    diffs = diferencias_con_original(machine_id)["diffs"]
    if tipos:
        diffs = diferencias_mod.filtrar_por_tipo(diffs, tipos)
    return diferencias_mod.a_filas_csv(profile, diffs)


def ruta_exportar(machine_id: str, cual: str) -> tuple[str, str]:
    """Ruta y nombre de archivo para descargar `actual.<ext>` (con los
    cambios) u `original.<ext>` (tal como se cargó la primera vez)."""
    if cual not in ("actual", "original"):
        raise ValueError("`cual` debe ser 'actual' u 'original'.")
    profile = cargar_perfil(machine_id)
    actual, original_path, _ = _rutas(profile)
    ruta = actual if cual == "actual" else original_path
    if not os.path.exists(ruta):
        raise FileNotFoundError(f"No existe el archivo '{cual}' de esta máquina.")
    nombre = f"{profile.id}_{cual}.{profile.extension}"
    return ruta, nombre
