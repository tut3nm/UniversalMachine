from __future__ import annotations

import io
import json

from fastapi import APIRouter, Form, HTTPException, UploadFile
from starlette.responses import StreamingResponse

from app.ai import llm
from app.ai.memoria import almacen
from app.routers._http import content_disposition
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


async def _archivos(**subidos: UploadFile | None) -> dict[str, svc.Archivo]:
    return {
        clave: svc.Archivo(nombre=archivo.filename or f"{clave}.txt", contenido=await archivo.read())
        for clave, archivo in subidos.items()
        if archivo is not None
    }


def _programa(programa: str):
    try:
        return json.loads(programa)
    except json.JSONDecodeError:
        raise HTTPException(400, "El programa no es JSON valido.")


@router.post("/interpretar")
async def interpretar(
    texto: str = Form(...),
    pantalla: str = Form(...),
    listado: UploadFile | None = None,
    datos: UploadFile | None = None,
    plantilla: UploadFile | None = None,
):
    """Pedido del usuario + archivos de la pantalla -> programa propuesto y
    vista previa, sin ejecutar nada todavia."""
    archivos = await _archivos(listado=listado, datos=datos, plantilla=plantilla)
    try:
        return svc.interpretar(pantalla, texto, archivos)
    except svc.AsistenteError as e:
        raise HTTPException(400, str(e))


@router.post("/previsualizar")
async def previsualizar(
    pantalla: str = Form(...),
    programa: str = Form(...),
    listado: UploadFile | None = None,
    datos: UploadFile | None = None,
    plantilla: UploadFile | None = None,
):
    """Vista previa de un programa editado en la tarjeta. No usa la IA."""
    archivos = await _archivos(listado=listado, datos=datos, plantilla=plantilla)
    try:
        return svc.previsualizar(pantalla, _programa(programa), archivos)
    except svc.AsistenteError as e:
        raise HTTPException(400, str(e))


@router.post("/ejecutar")
async def ejecutar(
    pantalla: str = Form(...),
    programa: str = Form(...),
    texto: str = Form(""),
    listado: UploadFile | None = None,
    datos: UploadFile | None = None,
    plantilla: UploadFile | None = None,
):
    """Ejecuta el programa que el usuario vio (y quizas edito) en la tarjeta
    y devuelve el archivo resultante (.zip o .xlsx segun la pantalla)."""
    archivos = await _archivos(listado=listado, datos=datos, plantilla=plantilla)
    try:
        salida = svc.ejecutar(pantalla, _programa(programa), archivos, texto_usuario=texto)
    except svc.AsistenteError as e:
        raise HTTPException(400, str(e))
    return StreamingResponse(
        io.BytesIO(salida.contenido), media_type=salida.media_type,
        headers={
            "Content-Disposition": content_disposition(salida.nombre),
            "X-Asistente-Resumen": json.dumps(salida.resumen),
        },
    )


# ---------------------------------------------------------------------------
# Memoria de formatos (PLAN_MEMORIA_FORMATOS.md). Fase 1: solo mediciones.
# ---------------------------------------------------------------------------


@router.post("/reconocer")
async def reconocer(
    pantalla: str = Form(...),
    listado: UploadFile | None = None,
    datos: UploadFile | None = None,
    plantilla: UploadFile | None = None,
):
    """Archivos de la pantalla -> formato reconocido (programa y vista previa
    ya aplicados) o ninguno. No usa la IA."""
    archivos = await _archivos(listado=listado, datos=datos, plantilla=plantilla)
    try:
        return svc.reconocer(pantalla, archivos)
    except svc.AsistenteError as e:
        raise HTTPException(400, str(e))


@router.post("/formatos")
async def guardar_formato(
    pantalla: str = Form(...),
    nombre: str = Form(...),
    programa: str = Form(...),
    explicacion: str = Form(""),
    formato_id: str | None = Form(None),
    listado: UploadFile | None = None,
    datos: UploadFile | None = None,
    plantilla: UploadFile | None = None,
):
    """Guarda (o actualiza, si viene `formato_id`) un formato a partir de un
    programa que el usuario ya confirmo en la tarjeta."""
    archivos = await _archivos(listado=listado, datos=datos, plantilla=plantilla)
    try:
        return svc.guardar_formato(
            pantalla, nombre, _programa(programa), explicacion, archivos, formato_id=formato_id
        )
    except svc.AsistenteError as e:
        raise HTTPException(400, str(e))


@router.get("/formatos")
def listar_formatos(pantalla: str | None = None):
    return [svc.formato_resumen(f) for f in almacen.listar(pantalla)]


@router.get("/formatos/{formato_id}")
def obtener_formato(formato_id: str):
    formato = almacen.obtener(formato_id)
    if formato is None:
        raise HTTPException(404, "Formato no encontrado.")
    return svc.formato_detalle(formato)


@router.patch("/formatos/{formato_id}")
def renombrar_formato(formato_id: str, nombre: str = Form(...)):
    try:
        formato = almacen.actualizar(formato_id, nombre=nombre)
    except ValueError as e:
        raise HTTPException(404, str(e))
    return svc.formato_resumen(formato)


@router.delete("/formatos/{formato_id}")
def borrar_formato(formato_id: str):
    if almacen.obtener(formato_id) is None:
        raise HTTPException(404, "Formato no encontrado.")
    almacen.borrar(formato_id)
    return {"ok": True}
