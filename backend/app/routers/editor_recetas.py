from __future__ import annotations

import io
import json

from fastapi import APIRouter, HTTPException, UploadFile
from starlette.responses import StreamingResponse

from app.services import editor_recetas_service as svc

router = APIRouter(prefix="/api/editor-recetas", tags=["editor-recetas"])


@router.post("/exportar")
async def exportar(csv: UploadFile):
    try:
        contenido = await csv.read()
        xlsx_bytes, nombre_xlsx, resumen = svc.exportar_excel(contenido, csv.filename or "receta.csv")
    except svc.EditorRecetasError as e:
        raise HTTPException(400, str(e))

    return StreamingResponse(
        io.BytesIO(xlsx_bytes),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={
            "Content-Disposition": f'attachment; filename="{nombre_xlsx}"',
            "X-Editor-Recetas-Resumen": json.dumps(resumen),
        },
    )


@router.post("/aplicar")
async def aplicar(csv_original: UploadFile, xlsx_editado: UploadFile):
    try:
        csv_bytes = await csv_original.read()
        xlsx_bytes = await xlsx_editado.read()
        return svc.previsualizar_cambios(
            csv_bytes, csv_original.filename or "receta.csv",
            xlsx_bytes, xlsx_editado.filename or "receta.xlsx",
        )
    except svc.EditorRecetasError as e:
        raise HTTPException(400, str(e))


@router.post("/aplicar/descargar")
async def aplicar_descargar(csv_original: UploadFile, xlsx_editado: UploadFile):
    try:
        csv_bytes = await csv_original.read()
        xlsx_bytes = await xlsx_editado.read()
        salida_bytes, nombre_salida, resumen = svc.aplicar_y_descargar(
            csv_bytes, csv_original.filename or "receta.csv",
            xlsx_bytes, xlsx_editado.filename or "receta.xlsx",
        )
    except svc.EditorRecetasError as e:
        raise HTTPException(400, str(e))

    return StreamingResponse(
        io.BytesIO(salida_bytes), media_type="text/csv",
        headers={
            "Content-Disposition": f'attachment; filename="{nombre_salida}"',
            "X-Editor-Recetas-Resumen": json.dumps(resumen),
        },
    )
