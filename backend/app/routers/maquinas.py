from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from app.services import maquinas_service as svc

router = APIRouter(prefix="/api/maquinas", tags=["maquinas"])

# Parámetros de filtro compartidos por el listado y por "todos los índices
# filtrados": los dos tienen que ver exactamente el mismo subconjunto.
_Q = Query("", description="Búsqueda libre sobre cualquier campo visible")
_RANGO = Query(None, description="Rango numérico 'campo:min:max' (repetible)")
_PLACEHOLDERS = Query(False, description="Incluir los slots vacíos")
_ORDEN = Query(None, description="Columna de orden: 'pos' o un campo visible")
_DIR = Query("asc", pattern="^(asc|desc)$")


class RegistroIn(BaseModel):
    valores: dict[str, Any]
    hash_esperado: str | None = None


@router.get("")
def listar():
    return svc.listar_maquinas()


@router.get("/{machine_id}")
def obtener(machine_id: str):
    try:
        return svc.obtener_maquina(machine_id)
    except svc.MaquinaNoEncontrada:
        raise HTTPException(404, f"No existe la máquina '{machine_id}'")


@router.get("/{machine_id}/registros")
def registros(
    machine_id: str,
    q: str = _Q,
    rango: list[str] | None = _RANGO,
    placeholders: bool = _PLACEHOLDERS,
    orden: str | None = _ORDEN,
    dir: str = _DIR,
    offset: int = Query(0, ge=0),
    limit: int = Query(200, ge=1, le=svc.LIMITE_MAXIMO),
):
    try:
        return svc.listar_registros(
            machine_id, q=q, rangos_crudos=rango, placeholders=placeholders,
            orden=orden, descendente=(dir == "desc"), offset=offset, limit=limit,
        )
    except svc.MaquinaNoEncontrada:
        raise HTTPException(404, f"No existe la máquina '{machine_id}'")
    except svc.FiltroInvalido as e:
        raise HTTPException(422, str(e))


@router.get("/{machine_id}/registros/indices")
def indices(
    machine_id: str,
    q: str = _Q,
    rango: list[str] | None = _RANGO,
    placeholders: bool = _PLACEHOLDERS,
    orden: str | None = _ORDEN,
    dir: str = _DIR,
):
    """Todos los índices que matchean el filtro actual, en el orden visible."""
    try:
        return svc.indices_filtrados(
            machine_id, q=q, rangos_crudos=rango, placeholders=placeholders,
            orden=orden, descendente=(dir == "desc"),
        )
    except svc.MaquinaNoEncontrada:
        raise HTTPException(404, f"No existe la máquina '{machine_id}'")
    except svc.FiltroInvalido as e:
        raise HTTPException(422, str(e))


@router.post("/{machine_id}/registros")
def crear(machine_id: str, body: RegistroIn):
    try:
        return svc.crear_registro(machine_id, body.valores, body.hash_esperado)
    except svc.MaquinaNoEncontrada:
        raise HTTPException(404, f"No existe la máquina '{machine_id}'")
    except svc.ConflictoEdicionExterna as e:
        raise HTTPException(409, str(e))
    except svc.ClaveDuplicada as e:
        raise HTTPException(409, str(e))
    except svc.ValoresInvalidos as e:
        raise HTTPException(422, str(e))


@router.put("/{machine_id}/registros/{index}")
def actualizar(machine_id: str, index: int, body: RegistroIn):
    try:
        return svc.actualizar_registro(machine_id, index, body.valores, body.hash_esperado)
    except svc.MaquinaNoEncontrada:
        raise HTTPException(404, f"No existe la máquina '{machine_id}'")
    except svc.ConflictoEdicionExterna as e:
        raise HTTPException(409, str(e))
    except svc.ClaveDuplicada as e:
        raise HTTPException(409, str(e))
    except svc.ValoresInvalidos as e:
        raise HTTPException(422, str(e))
    except IndexError as e:
        raise HTTPException(404, str(e))


class BorrarIn(BaseModel):
    hash_esperado: str | None = None


@router.delete("/{machine_id}/registros/{index}")
def eliminar(machine_id: str, index: int, body: BorrarIn):
    try:
        return svc.eliminar_registro(machine_id, index, body.hash_esperado)
    except svc.MaquinaNoEncontrada:
        raise HTTPException(404, f"No existe la máquina '{machine_id}'")
    except svc.ConflictoEdicionExterna as e:
        raise HTTPException(409, str(e))
    except IndexError as e:
        raise HTTPException(404, str(e))


class BulkEditIn(BaseModel):
    indices: list[int]
    campo: str
    valor: str
    hash_esperado: str | None = None


@router.post("/{machine_id}/registros/bulk-edit")
def bulk_edit(machine_id: str, body: BulkEditIn):
    """Aplica el mismo valor a un parámetro de varios registros a la vez —
    equivalente de `BulkEditDialog` (máquina232/src/app.py:2673)."""
    try:
        return svc.editar_en_masa(
            machine_id, body.indices, body.campo, body.valor, body.hash_esperado)
    except svc.MaquinaNoEncontrada:
        raise HTTPException(404, f"No existe la máquina '{machine_id}'")
    except svc.ConflictoEdicionExterna as e:
        raise HTTPException(409, str(e))
    except svc.ValoresInvalidos as e:
        raise HTTPException(422, str(e))
    except IndexError as e:
        raise HTTPException(404, str(e))


class BulkDeleteIn(BaseModel):
    indices: list[int]
    hash_esperado: str | None = None


@router.post("/{machine_id}/registros/bulk-delete")
def bulk_delete(machine_id: str, body: BulkDeleteIn):
    """Baja de varios registros en una sola operación — equivalente de
    `_delete_indices` (máquina232/src/app.py:3806)."""
    try:
        return svc.eliminar_en_masa(machine_id, body.indices, body.hash_esperado)
    except svc.MaquinaNoEncontrada:
        raise HTTPException(404, f"No existe la máquina '{machine_id}'")
    except svc.ConflictoEdicionExterna as e:
        raise HTTPException(409, str(e))
    except IndexError as e:
        raise HTTPException(404, str(e))


@router.get("/{machine_id}/salud")
def salud(machine_id: str):
    try:
        return svc.salud_maquina(machine_id)
    except svc.MaquinaNoEncontrada:
        raise HTTPException(404, f"No existe la máquina '{machine_id}'")


class FiltroIn(BaseModel):
    nombre: str
    busqueda: str = ""
    rangos: list[str] = []


@router.get("/{machine_id}/filtros")
def filtros_get(machine_id: str):
    try:
        return svc.listar_filtros(machine_id)
    except svc.MaquinaNoEncontrada:
        raise HTTPException(404, f"No existe la máquina '{machine_id}'")


@router.post("/{machine_id}/filtros")
def filtros_post(machine_id: str, body: FiltroIn):
    if not body.nombre.strip():
        raise HTTPException(422, "El filtro necesita un nombre.")
    try:
        return svc.guardar_filtro(machine_id, body.nombre.strip(), body.busqueda, body.rangos)
    except svc.MaquinaNoEncontrada:
        raise HTTPException(404, f"No existe la máquina '{machine_id}'")
    except svc.FiltroInvalido as e:
        raise HTTPException(422, str(e))


@router.delete("/{machine_id}/filtros/{nombre}")
def filtros_delete(machine_id: str, nombre: str):
    try:
        return svc.eliminar_filtro(machine_id, nombre)
    except svc.MaquinaNoEncontrada:
        raise HTTPException(404, f"No existe la máquina '{machine_id}'")
