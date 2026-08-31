"""Panel multi-máquina (Nivel 4.9 del plan de mejoras).

Vista consolidada, de una sola pasada, de todas las máquinas configuradas:
última modificación, cantidad de registros, duplicados pendientes de
revisar y alertas de salud. Útil recién cuando hay varias máquinas — con
una o dos, la ventana principal ya alcanza.

Cada máquina se lee de forma independiente y best-effort: un problema en
UNA (archivo corrupto, perfil roto) no debe impedir mostrar el resto."""

from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import datetime

import paths
import salud
from datastore import DataStore
from metadata import Sidecar
from profile import Profile


@dataclass
class ResumenMaquina:
    id: str
    nombre: str
    ultima_modificacion: str | None = None
    cantidad_registros: int | None = None
    duplicados_pendientes: int | None = None
    alertas_salud: int | None = None
    error: str | None = None


def resumen_de_maquina(profile: Profile) -> ResumenMaquina:
    data_dir = paths.data_dir_for(profile.id)
    path_actual = os.path.join(data_dir, f"actual.{profile.extension}")

    if not os.path.exists(path_actual):
        return ResumenMaquina(profile.id, profile.nombre, error="sin datos todavía")

    try:
        store = DataStore.load(path_actual, profile)
    except (OSError, ValueError, UnicodeDecodeError, LookupError) as exc:
        return ResumenMaquina(profile.id, profile.nombre, error=str(exc))

    mtime = datetime.fromtimestamp(os.path.getmtime(path_actual)).isoformat(timespec="seconds")
    cantidad = store.count_real() if profile.placeholder_regex() else len(store.records)

    sidecar = Sidecar.load(os.path.join(data_dir, "meta.json"))
    duplicados = 0
    if profile.duplicados_config():
        excluidas = sidecar.keys_with("no_duplicado")
        grupos = store.find_similar_groups(excluded_keys=excluidas)
        duplicados = sum(len(g) for g in grupos)

    alertas = len(salud.evaluar_salud(store, sidecar))

    return ResumenMaquina(profile.id, profile.nombre, ultima_modificacion=mtime,
                          cantidad_registros=cantidad, duplicados_pendientes=duplicados,
                          alertas_salud=alertas)


def resumen_de_todas(profiles: list[Profile]) -> list[ResumenMaquina]:
    return [resumen_de_maquina(p) for p in profiles]
