"""Servicio de duplicados (B4 de PLAN_PARIDAD_UI.md) — equivalente de
`DuplicatesDialog` del escritorio: agrupa
registros con código parecido según el método de duplicados del perfil
(`DataStore.find_similar_groups`), deja marcar un código como revisado
("no es duplicado", guardado en el sidecar de metadatos) y borrar los que
sí lo son."""

from __future__ import annotations

from typing import Any

from app import _bootstrap  # noqa: F401

from metadata import Sidecar

from app.services.maquinas_service import (  # reutiliza resolución de rutas/perfil y la baja en masa
    MaquinaNoEncontrada,
    _cargar_store_cacheado,
    _rutas,
    cargar_perfil,
    eliminar_en_masa,
)

__all__ = ["MaquinaNoEncontrada", "listar_duplicados", "marcar_no_duplicado", "eliminar_duplicados"]


def _sidecar(profile) -> Sidecar:
    _, _, meta = _rutas(profile)
    return Sidecar.load(meta)


def listar_duplicados(machine_id: str) -> dict[str, Any]:
    profile = cargar_perfil(machine_id)
    store = _cargar_store_cacheado(profile)  # es una consulta, no una mutación
    excluidas = _sidecar(profile).keys_with("no_duplicado")
    grupos = store.find_similar_groups(excluded_keys=excluidas)
    salida = []
    for grupo in grupos:
        registros = [
            {"index": idx, "code": store.key_of(store.records[idx]),
             "valores": dict(store.records[idx]), "revisado": False}
            for idx in grupo
        ]
        salida.append({"registros": registros})
    return {"grupos": salida}


def marcar_no_duplicado(machine_id: str, code: str) -> dict[str, Any]:
    """Marca `code` como revisado ("no es duplicado", app.py:1526): no
    vuelve a aparecer en futuras búsquedas de duplicados de esta máquina.
    Devuelve la lista de grupos ya actualizada, sin `code`."""
    profile = cargar_perfil(machine_id)
    sidecar = _sidecar(profile)
    sidecar.set(code, "no_duplicado", True)
    sidecar.save()
    return listar_duplicados(machine_id)


def eliminar_duplicados(machine_id: str, indices: list[int],
                        hash_esperado: str | None = None) -> dict[str, Any]:
    """Borra los registros marcados como duplicados reales. Es la misma
    operación que la baja en masa (B2): un solo backup, un evento de
    historial por registro."""
    return eliminar_en_masa(machine_id, indices, hash_esperado)
