from __future__ import annotations

from pydantic import BaseModel

from fastapi import APIRouter, HTTPException

from app.services import duplicados_service as svc
from app.services import maquinas_service as maq_svc

router = APIRouter(prefix="/api/maquinas/{machine_id}/duplicados", tags=["duplicados"])


@router.get("")
def duplicados(machine_id: str):
    try:
        return svc.listar_duplicados(machine_id)
    except maq_svc.MaquinaNoEncontrada:
        raise HTTPException(404, f"No existe la máquina '{machine_id}'")


class NoDuplicadoIn(BaseModel):
    code: str


@router.post("/no-duplicado")
def no_duplicado(machine_id: str, body: NoDuplicadoIn):
    try:
        return svc.marcar_no_duplicado(machine_id, body.code)
    except maq_svc.MaquinaNoEncontrada:
        raise HTTPException(404, f"No existe la máquina '{machine_id}'")


class EliminarDuplicadosIn(BaseModel):
    indices: list[int]
    hash_esperado: str | None = None


@router.post("/eliminar")
def eliminar(machine_id: str, body: EliminarDuplicadosIn):
    try:
        return svc.eliminar_duplicados(machine_id, body.indices, body.hash_esperado)
    except maq_svc.MaquinaNoEncontrada:
        raise HTTPException(404, f"No existe la máquina '{machine_id}'")
    except maq_svc.ConflictoEdicionExterna as e:
        raise HTTPException(409, str(e))
    except IndexError as e:
        raise HTTPException(404, str(e))
