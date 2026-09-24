from __future__ import annotations

import io

from fastapi import APIRouter, HTTPException, UploadFile
from starlette.responses import StreamingResponse

from app.routers._http import content_disposition
from app.services import plantillas_masivas_service as svc

router = APIRouter(prefix="/api/plantillas-masivas", tags=["plantillas-masivas"])


@router.post("/previsualizar")
async def previsualizar(plantilla: UploadFile, listado: UploadFile):
    try:
        plantilla_bytes = await plantilla.read()
        listado_bytes = await listado.read()
        return svc.previsualizar(
            plantilla_bytes, plantilla.filename or "plantilla.txt",
            listado_bytes, listado.filename or "listado.txt",
        )
    except svc.PlantillasMasivasError as e:
        raise HTTPException(400, str(e))


@router.post("/generar")
async def generar(plantilla: UploadFile, listado: UploadFile):
    try:
        plantilla_bytes = await plantilla.read()
        listado_bytes = await listado.read()
        zip_bytes, nombre_zip = svc.generar_zip(
            plantilla_bytes, plantilla.filename or "plantilla.txt",
            listado_bytes, listado.filename or "listado.txt",
        )
    except svc.PlantillasMasivasError as e:
        raise HTTPException(400, str(e))

    return StreamingResponse(
        io.BytesIO(zip_bytes), media_type="application/zip",
        headers={"Content-Disposition": content_disposition(nombre_zip)},
    )
