from __future__ import annotations

import csv
import io

from fastapi import APIRouter, HTTPException, Query
from starlette.responses import FileResponse, StreamingResponse

from app.routers._http import content_disposition
from app.services import consulta_service as svc
from app.services import maquinas_service as maq_svc

router = APIRouter(prefix="/api/maquinas/{machine_id}", tags=["consulta"])


@router.get("/backups")
def backups(machine_id: str):
    try:
        return svc.listar_backups(machine_id)
    except maq_svc.MaquinaNoEncontrada:
        raise HTTPException(404, f"No existe la máquina '{machine_id}'")


@router.get("/backups/{nombre_backup}/preview")
def backup_preview(machine_id: str, nombre_backup: str):
    try:
        return svc.backup_preview(machine_id, nombre_backup)
    except maq_svc.MaquinaNoEncontrada:
        raise HTTPException(404, f"No existe la máquina '{machine_id}'")
    except FileNotFoundError as e:
        raise HTTPException(404, str(e))


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


@router.post("/restaurar-original")
def restaurar_original(machine_id: str):
    try:
        return svc.restaurar_original(machine_id)
    except maq_svc.MaquinaNoEncontrada:
        raise HTTPException(404, f"No existe la máquina '{machine_id}'")
    except FileNotFoundError as e:
        raise HTTPException(404, str(e))


@router.get("/undo-state")
def undo_state(machine_id: str):
    try:
        maq_svc.cargar_perfil(machine_id)  # 404 si la máquina no existe
    except maq_svc.MaquinaNoEncontrada:
        raise HTTPException(404, f"No existe la máquina '{machine_id}'")
    return maq_svc.estado_deshacer(machine_id)


@router.post("/deshacer")
def deshacer(machine_id: str):
    try:
        return maq_svc.deshacer(machine_id)
    except maq_svc.MaquinaNoEncontrada:
        raise HTTPException(404, f"No existe la máquina '{machine_id}'")
    except maq_svc.SinNadaQueDeshacer as e:
        raise HTTPException(409, str(e))
    except maq_svc.ConflictoEdicionExterna as e:
        raise HTTPException(409, str(e))


@router.post("/rehacer")
def rehacer(machine_id: str):
    try:
        return maq_svc.rehacer(machine_id)
    except maq_svc.MaquinaNoEncontrada:
        raise HTTPException(404, f"No existe la máquina '{machine_id}'")
    except maq_svc.SinNadaQueRehacer as e:
        raise HTTPException(409, str(e))
    except maq_svc.ConflictoEdicionExterna as e:
        raise HTTPException(409, str(e))


@router.get("/historial")
def historial(machine_id: str, limite: int = 200, codigo: str | None = None,
             accion: str | None = None, desde: int | None = None):
    try:
        return svc.listar_historial(machine_id, limite, codigo, accion, desde)
    except maq_svc.MaquinaNoEncontrada:
        raise HTTPException(404, f"No existe la máquina '{machine_id}'")


@router.get("/historial/informe.csv")
def historial_informe(machine_id: str, codigo: str | None = None,
                      accion: str | None = None, desde: int | None = None):
    try:
        filas = svc.historial_informe_filas(machine_id, codigo, accion, desde)
    except maq_svc.MaquinaNoEncontrada:
        raise HTTPException(404, f"No existe la máquina '{machine_id}'")
    return _csv_response(filas, "informe_cambios.csv")


@router.get("/diferencias")
def diferencias(machine_id: str):
    try:
        return svc.diferencias_con_original(machine_id)
    except maq_svc.MaquinaNoEncontrada:
        raise HTTPException(404, f"No existe la máquina '{machine_id}'")


@router.get("/diferencias/informe.csv")
def diferencias_informe(machine_id: str, tipo: list[str] = Query(default=[])):
    try:
        filas = svc.diferencias_informe_filas(machine_id, set(tipo) or None)
    except maq_svc.MaquinaNoEncontrada:
        raise HTTPException(404, f"No existe la máquina '{machine_id}'")
    return _csv_response(filas, "cambios.csv")


@router.get("/exportar")
def exportar(machine_id: str, cual: str = "actual"):
    try:
        ruta, nombre = svc.ruta_exportar(machine_id, cual)
    except maq_svc.MaquinaNoEncontrada:
        raise HTTPException(404, f"No existe la máquina '{machine_id}'")
    except FileNotFoundError as e:
        raise HTTPException(404, str(e))
    except ValueError as e:
        raise HTTPException(422, str(e))
    return FileResponse(ruta, filename=nombre)


def _csv_response(filas: list[list[str]], nombre_archivo: str) -> StreamingResponse:
    buf = io.StringIO()
    buf.write("﻿")  # BOM: mismo utf-8-sig que usa el escritorio para que Excel lo abra bien
    csv.writer(buf).writerows(filas)
    buf.seek(0)
    return StreamingResponse(
        buf, media_type="text/csv",
        headers={"Content-Disposition": content_disposition(nombre_archivo)},
    )
