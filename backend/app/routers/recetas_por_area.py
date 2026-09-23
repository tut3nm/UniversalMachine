from __future__ import annotations

import io

from fastapi import APIRouter, HTTPException, UploadFile
from starlette.responses import StreamingResponse

from app.services import recetas_por_area_service as svc

router = APIRouter(prefix="/api/recetas-por-area", tags=["recetas-por-area"])


@router.post("/previsualizar")
async def previsualizar(listado: UploadFile):
    try:
        listado_bytes = await listado.read()
        return svc.previsualizar(listado_bytes, listado.filename or "listado.txt")
    except svc.RecetasPorAreaError as e:
        raise HTTPException(400, str(e))


@router.post("/auditar")
def auditar():
    try:
        return svc.auditar_repositorio()
    except svc.RecetasPorAreaError as e:
        raise HTTPException(400, str(e))


@router.post("/generar")
async def generar(listado: UploadFile):
    try:
        listado_bytes = await listado.read()
        zip_bytes, nombre_zip = svc.generar_zip(listado_bytes, listado.filename or "listado.txt")
    except svc.RecetasPorAreaError as e:
        raise HTTPException(400, str(e))

    return StreamingResponse(
        io.BytesIO(zip_bytes), media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{nombre_zip}"'},
    )
