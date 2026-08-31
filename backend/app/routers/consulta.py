from __future__ import annotations

from fastapi import APIRouter, HTTPException

from app.services import consulta_service as svc
from app.services import maquinas_service as maq_svc

router = APIRouter(prefix="/api/maquinas/{machine_id}", tags=["consulta"])


@router.get("/backups")
def backups(machine_id: str):
    try:
        return svc.listar_backups(machine_id)
    except maq_svc.MaquinaNoEncontrada:
        raise HTTPException(404, f"No existe la máquina '{machine_id}'")


@router.post("/backups/{nombre_backup}/restaurar")
def restaurar(machine_id: str, nombre_backup: str):
    try:
        return svc.restaurar_backup(machine_id, nombre_backup)
    except maq_svc.MaquinaNoEncontrada:
        raise HTTPException(404, f"No existe la máquina '{machine_id}'")
    except FileNotFoundError as e:
        raise HTTPException(404, str(e))
    except ValueError as e:
        raise HTTPException(409, str(e))


@router.get("/historial")
def historial(machine_id: str, limite: int = 200):
    try:
        return svc.listar_historial(machine_id, limite)
    except maq_svc.MaquinaNoEncontrada:
        raise HTTPException(404, f"No existe la máquina '{machine_id}'")


@router.get("/diferencias")
def diferencias(machine_id: str):
    try:
        return svc.diferencias_con_original(machine_id)
    except maq_svc.MaquinaNoEncontrada:
        raise HTTPException(404, f"No existe la máquina '{machine_id}'")
