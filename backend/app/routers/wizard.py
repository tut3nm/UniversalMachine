from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, UploadFile
from pydantic import BaseModel

from app.services import wizard_service as svc

router = APIRouter(prefix="/api/wizard", tags=["wizard"])


@router.post("/start")
async def start(file: UploadFile | None = None, profile_id: str | None = None):
    try:
        if profile_id:
            return svc.iniciar_edicion(profile_id)
        if not file:
            raise HTTPException(400, "Falta el archivo CSV de muestra (alta) o profile_id (edición)")
        contenido = await file.read()
        return svc.iniciar_alta(file.filename or "muestra.csv", contenido)
    except svc.WizardError as e:
        raise HTTPException(400, str(e))


class ClasificarIn(BaseModel):
    wizard_id: str
    orientacion: str  # "columnas" | "filas"
    primera_col: int = 1


@router.post("/classify-rows")
def classify_rows(body: ClasificarIn):
    try:
        return svc.clasificar(body.wizard_id, body.orientacion, body.primera_col)
    except KeyError as e:
        raise HTTPException(404, str(e))


class FilaWizard(BaseModel):
    idx: int
    incluir: bool = False
    nombre: str | None = None
    titulo: str | None = None
    etiqueta: str | None = None
    tipo: str = "texto"
    formato: dict[str, Any] = {}
    min: float | None = None
    max: float | None = None
    default: Any = None
    kind_override: str | None = None


class BuildProfileIn(BaseModel):
    wizard_id: str
    machine_id: str
    nombre: str
    descripcion: str = ""
    clave_idx: int
    filas: list[FilaWizard]


@router.post("/build-profile")
def build_profile(body: BuildProfileIn):
    try:
        return svc.construir_perfil(
            body.wizard_id, body.machine_id, body.nombre, body.descripcion,
            body.clave_idx, [f.model_dump() for f in body.filas],
        )
    except KeyError as e:
        raise HTTPException(404, str(e))
    except svc.WizardError as e:
        raise HTTPException(400, str(e))


class WizardIdIn(BaseModel):
    wizard_id: str


@router.post("/validate")
def validate(body: WizardIdIn):
    try:
        return svc.validar(body.wizard_id)
    except KeyError as e:
        raise HTTPException(404, str(e))
    except svc.WizardError as e:
        raise HTTPException(400, str(e))


@router.post("/confirm")
def confirm(body: WizardIdIn):
    try:
        return svc.confirmar(body.wizard_id)
    except KeyError as e:
        raise HTTPException(404, str(e))
    except svc.WizardError as e:
        raise HTTPException(400, str(e))
