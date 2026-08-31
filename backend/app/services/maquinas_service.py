"""Capa de servicio: adapta profile.py/datastore.py/backups.py/historial.py
(Python puro, dataclasses) a dicts JSON-friendly para los routers de
FastAPI. Sigue el modelo "sin estado entre requests": cada operación
carga el DataStore desde disco, opera, guarda — no hay un DataStore vivo
en memoria del proceso (a diferencia de la app Tkinter). Esto es a
propósito: permite múltiples pestañas/clientes sin sincronizar estado de
sesión, al costo de recargar el archivo en cada request (aceptable para
los tamaños de catálogo actuales, cientos-miles de registros)."""

from __future__ import annotations

import dataclasses
import os
from typing import Any

from app import _bootstrap  # noqa: F401  (side effect: agrega app/core/ a sys.path)

import arranque
import backups as backups_mod
import deteccion_externa
import historial as historial_mod
import panel_multi_maquina
import paths
import salud as salud_mod
from datastore import DataStore
from metadata import Sidecar
from profile import Profile, ProfileError
from validacion import validar_valores_de_registro

APP_VERSION = "webapp-0.1.0"


class MaquinaNoEncontrada(Exception):
    pass


class ConflictoEdicionExterna(Exception):
    """El archivo en disco cambió desde el último hash conocido del cliente."""


class ValoresInvalidos(Exception):
    def __init__(self, errores: list):
        self.errores = errores
        super().__init__("; ".join(f"{e.titulo_ui}: {e.mensaje}" for e in errores))


def _perfil_path(machine_id: str) -> str:
    return os.path.join(paths.profiles_dir(), f"maquina_{machine_id}.json")


def _rutas(profile: Profile) -> tuple[str, str, str]:
    d = paths.data_dir_for(profile.id)
    ext = profile.extension
    return (
        os.path.join(d, f"actual.{ext}"),
        os.path.join(d, f"original.{ext}"),
        os.path.join(d, "meta.json"),
    )


def _listar_ids() -> list[str]:
    pdir = paths.profiles_dir()
    ids = []
    for name in os.listdir(pdir):
        if name.startswith("maquina_") and name.endswith(".json"):
            ids.append(name[len("maquina_"):-len(".json")])
    return sorted(ids)


def cargar_perfil(machine_id: str) -> Profile:
    path = _perfil_path(machine_id)
    if not os.path.exists(path):
        raise MaquinaNoEncontrada(machine_id)
    return Profile.load(path)


def _asegurar_sembrado(profile: Profile) -> None:
    actual, original, meta = _rutas(profile)
    if not os.path.exists(actual):
        arranque.seed_or_migrate(profile, original, actual, meta)


def _cargar_store(profile: Profile) -> DataStore:
    _asegurar_sembrado(profile)
    actual, _, _ = _rutas(profile)
    return DataStore.load(actual, profile)


def listar_maquinas() -> list[dict[str, Any]]:
    perfiles = []
    for mid in _listar_ids():
        try:
            perfiles.append(cargar_perfil(mid))
        except ProfileError:
            continue
    resumenes = panel_multi_maquina.resumen_de_todas(perfiles)
    return [dataclasses.asdict(r) for r in resumenes]


def obtener_maquina(machine_id: str) -> dict[str, Any]:
    profile = cargar_perfil(machine_id)
    return {
        "id": profile.id,
        "nombre": profile.nombre,
        "descripcion": profile.descripcion,
        "campos": [dataclasses.asdict(c) for c in profile.campos_visibles()],
    }


def listar_registros(machine_id: str) -> dict[str, Any]:
    profile = cargar_perfil(machine_id)
    store = _cargar_store(profile)
    actual, _, _ = _rutas(profile)
    campos_visibles = {c.nombre_interno for c in profile.campos_visibles()}
    registros = []
    for i, rec in enumerate(store.records):
        registros.append({
            "index": i,
            "es_placeholder": store.is_placeholder(rec),
            **{k: v for k, v in rec.items() if k in campos_visibles},
        })
    return {
        "registros": registros,
        "total": len(store.records),
        "reales": store.count_real(),
        "hash": deteccion_externa.hash_archivo(actual) if os.path.exists(actual) else None,
    }


_ACCION_HISTORIAL = {"alta": "alta", "edicion": "modificacion", "baja": "baja"}


def _guardar_con_backup(profile: Profile, store: DataStore, accion: str,
                         clave: str, antes: dict | None, despues: dict | None,
                         hash_esperado: str | None) -> str:
    actual, _, _ = _rutas(profile)
    if hash_esperado is not None and os.path.exists(actual):
        if deteccion_externa.fue_modificado_externamente(actual, hash_esperado):
            raise ConflictoEdicionExterna(
                "El archivo fue modificado por fuera de la app desde la última carga.")
    data_dir = paths.data_dir_for(profile.id)
    backups_mod.crear_backup(data_dir, actual, profile.extension)
    store.save(actual)
    historial_mod.registrar(
        os.path.join(data_dir, "historial.jsonl"),
        accion=_ACCION_HISTORIAL[accion], clave=clave,
        anteriores=antes, nuevos=despues, origen="webapp", version=APP_VERSION,
    )
    return deteccion_externa.hash_archivo(actual)


def crear_registro(machine_id: str, valores: dict[str, Any],
                    hash_esperado: str | None = None) -> dict[str, Any]:
    profile = cargar_perfil(machine_id)
    errores = validar_valores_de_registro(profile, valores)
    if errores:
        raise ValoresInvalidos(errores)
    store = _cargar_store(profile)
    nuevo = store.nuevo_registro(valores)
    store.add(nuevo)
    idx = len(store.records) - 1
    nuevo_hash = _guardar_con_backup(profile, store, "alta", store.key_of(nuevo),
                                      None, nuevo, hash_esperado)
    return {"index": idx, "registro": nuevo, "hash": nuevo_hash}


def actualizar_registro(machine_id: str, index: int, valores: dict[str, Any],
                         hash_esperado: str | None = None) -> dict[str, Any]:
    profile = cargar_perfil(machine_id)
    errores = validar_valores_de_registro(profile, valores)
    if errores:
        raise ValoresInvalidos(errores)
    store = _cargar_store(profile)
    if index < 0 or index >= len(store.records):
        raise IndexError(f"No existe el registro {index}")
    antes = dict(store.records[index])
    store.update(index, valores)
    despues = dict(store.records[index])
    nuevo_hash = _guardar_con_backup(profile, store, "edicion", store.key_of(despues),
                                      antes, despues, hash_esperado)
    return {"index": index, "registro": despues, "hash": nuevo_hash}


def eliminar_registro(machine_id: str, index: int,
                       hash_esperado: str | None = None) -> dict[str, Any]:
    profile = cargar_perfil(machine_id)
    store = _cargar_store(profile)
    if index < 0 or index >= len(store.records):
        raise IndexError(f"No existe el registro {index}")
    antes = dict(store.records[index])
    store.delete(index)
    nuevo_hash = _guardar_con_backup(profile, store, "baja", store.key_of(antes),
                                      antes, None, hash_esperado)
    return {"hash": nuevo_hash}


def salud_maquina(machine_id: str) -> dict[str, Any]:
    profile = cargar_perfil(machine_id)
    store = _cargar_store(profile)
    _, _, meta = _rutas(profile)
    sidecar = Sidecar.load(meta)
    hallazgos = salud_mod.evaluar_salud(store, sidecar)
    return {"hallazgos": [dataclasses.asdict(h) for h in hallazgos]}
