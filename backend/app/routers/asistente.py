from __future__ import annotations

import io
import json

from fastapi import APIRouter, Form, HTTPException, UploadFile
from starlette.responses import StreamingResponse

from app.ai import llm
from app.services import asistente_service as svc

router = APIRouter(prefix="/api/asistente", tags=["asistente"])


@router.get("/estado")
def estado():
    """Mismo criterio que /api/mediciones/estado, mas si el llama-server
    persistente esta arriba (vs. el fallback por subprocess de la fase 1)."""
    ok, mensaje = llm.is_available()
    return {
        "disponible": ok,
        "mensaje": mensaje,
        "server_activo": llm.server_is_running(),
    }


@router.post("/interpretar")
async def interpretar(texto: str = Form(...), listado: UploadFile | None = None):
    """Arma la PlanCard: interpreta el pedido y devuelve el programa DSL
    propuesto, sin ejecutar nada todavia."""
    listado_bytes = await listado.read() if listado else None
    listado_nombre = listado.filename if listado else None
    try:
        return svc.interpretar(texto, listado_bytes, listado_nombre)
    except svc.AsistenteError as e:
        raise HTTPException(400, str(e))


@router.post("/ejecutar")
async def ejecutar(
    programa: str = Form(...),
    listado: UploadFile = None,
    texto: str = Form(""),
):
    """Ejecuta un programa (el que el usuario vio y eventualmente edito en
    la PlanCard) y devuelve el .zip resultante."""
    if listado is None:
        raise HTTPException(400, "Falta el listado.")
    try:
        programa_data = json.loads(programa)
    except json.JSONDecodeError:
        raise HTTPException(400, "El programa no es JSON valido.")

    listado_bytes = await listado.read()
    try:
        zip_bytes, nombre_zip, resumen = svc.ejecutar(
            programa_data, listado_bytes, listado.filename or "listado.txt", texto_usuario=texto,
        )
    except svc.AsistenteError as e:
        raise HTTPException(400, str(e))

    return StreamingResponse(
        io.BytesIO(zip_bytes), media_type="application/zip",
        headers={
            "Content-Disposition": f'attachment; filename="{nombre_zip}"',
            "X-Asistente-Resumen": json.dumps(resumen),
        },
    )
