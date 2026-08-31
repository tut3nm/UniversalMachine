from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.services import maquinas_service as svc

router = APIRouter(prefix="/api/maquinas", tags=["maquinas"])


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
def registros(machine_id: str):
    try:
        return svc.listar_registros(machine_id)
    except svc.MaquinaNoEncontrada:
        raise HTTPException(404, f"No existe la máquina '{machine_id}'")


@router.post("/{machine_id}/registros")
def crear(machine_id: str, body: RegistroIn):
    try:
        return svc.crear_registro(machine_id, body.valores, body.hash_esperado)
    except svc.MaquinaNoEncontrada:
        raise HTTPException(404, f"No existe la máquina '{machine_id}'")
    except svc.ConflictoEdicionExterna as e:
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


@router.get("/{machine_id}/salud")
def salud(machine_id: str):
    try:
        return svc.salud_maquina(machine_id)
    except svc.MaquinaNoEncontrada:
        raise HTTPException(404, f"No existe la máquina '{machine_id}'")
