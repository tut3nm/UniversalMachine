"""Endpoints de sólo lectura (+ restaurar backup) para Backups, Historial y
Diferencias contra el original — Fase 1 del plan expone lectura; el resto
de las acciones de estos diálogos (deshacer/rehacer, exportar CSV desde la
UI, etc.) quedan para Fase 2, ver PLAN_WEBAPP.md."""

from __future__ import annotations

import dataclasses
import os
from typing import Any

from app import _bootstrap  # noqa: F401

import backups as backups_mod
import deteccion_externa
import diferencias as diferencias_mod
import historial as historial_mod
import paths
from datastore import DataStore

from app.services.maquinas_service import (  # reutiliza la resolución de rutas/perfil
    MaquinaNoEncontrada,
    _cargar_store,
    _rutas,
    cargar_perfil,
)


def _asdict_backup(b) -> dict[str, Any]:
    d = dataclasses.asdict(b)
    d["timestamp"] = b.timestamp.isoformat()
    d["ruta_hash"] = b.ruta_hash
    return d


def listar_backups(machine_id: str) -> list[dict[str, Any]]:
    profile = cargar_perfil(machine_id)
    data_dir = paths.data_dir_for(profile.id)
    return [_asdict_backup(b) for b in backups_mod.listar_backups(data_dir)]


def restaurar_backup(machine_id: str, nombre_backup: str) -> dict[str, Any]:
    profile = cargar_perfil(machine_id)
    data_dir = paths.data_dir_for(profile.id)
    candidatos = [b for b in backups_mod.listar_backups(data_dir) if b.nombre == nombre_backup]
    if not candidatos:
        raise FileNotFoundError(f"No existe el backup '{nombre_backup}'")
    backup = candidatos[0]
    if not backups_mod.verificar_integridad(backup):
        raise ValueError(f"El backup '{nombre_backup}' no pasa la verificación de integridad (hash)")
    actual, _, _ = _rutas(profile)
    backups_mod.crear_backup(data_dir, actual, profile.extension)  # respalda el estado actual también
    backups_mod.restaurar_backup(backup, actual)
    historial_mod.registrar(
        os.path.join(data_dir, "historial.jsonl"), accion="restauracion",
        clave=nombre_backup, origen="webapp",
    )
    return {"hash": deteccion_externa.hash_archivo(actual)}


def listar_historial(machine_id: str, limite: int = 200) -> list[dict[str, Any]]:
    profile = cargar_perfil(machine_id)
    data_dir = paths.data_dir_for(profile.id)
    eventos = historial_mod.leer_eventos(os.path.join(data_dir, "historial.jsonl"))
    return eventos[-limite:][::-1]


def diferencias_con_original(machine_id: str) -> dict[str, Any]:
    profile = cargar_perfil(machine_id)
    store_actual = _cargar_store(profile)
    _, original_path, _ = _rutas(profile)
    if not os.path.exists(original_path):
        return {"diffs": []}
    store_original = DataStore.load(original_path, profile)
    diffs = diferencias_mod.comparar_con_original(store_actual, store_original)
    return {"diffs": diffs}
