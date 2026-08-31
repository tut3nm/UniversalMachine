from __future__ import annotations

import os
import tempfile

from fastapi import APIRouter, Form, HTTPException, UploadFile
from starlette.responses import FileResponse

from app.services import mediciones_service as svc

router = APIRouter(prefix="/api/mediciones", tags=["mediciones"])


@router.get("/estado")
def estado():
    return svc.estado_ia()


@router.post("/procesar")
async def procesar(
    archivo: UploadFile,
    anotaciones: UploadFile | None = None,
    use_ai: bool = Form(True),
):
    contenido = await archivo.read()
    contenido_anot = await anotaciones.read() if anotaciones else None
    nombre_anot = anotaciones.filename if anotaciones else None
    try:
        resultado = svc.procesar(
            archivo.filename or "mediciones.txt", contenido,
            nombre_anot, contenido_anot, use_ai=use_ai,
        )
    except ValueError as e:
        raise HTTPException(400, str(e))
    return {k: v for k, v in resultado.items() if k not in ("out_path",)} | {
        "download_url": f"/api/mediciones/descargar?path={resultado['out_path']}"
    }


@router.get("/descargar")
def descargar(path: str):
    # Sólo se sirven archivos generados por /procesar en el temp dir del
    # propio proceso: no se acepta una ruta arbitraria del cliente.
    tmp_root = os.path.realpath(tempfile.gettempdir())
    real = os.path.realpath(path)
    if not real.startswith(tmp_root) or "mediciones_" not in real:
        raise HTTPException(400, "Ruta no permitida")
    if not os.path.exists(real):
        raise HTTPException(404, "El archivo ya no existe (temporal)")
    return FileResponse(real, filename=os.path.basename(real))
