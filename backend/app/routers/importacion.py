from __future__ import annotations

from fastapi import APIRouter, HTTPException, UploadFile
from pydantic import BaseModel

from app.services import import_service as svc
from app.services import maquinas_service as maq_svc

router = APIRouter(prefix="/api/maquinas/{machine_id}/import", tags=["importacion"])


@router.post("/start")
async def start(machine_id: str, file: UploadFile):
    try:
        contenido = await file.read()
        return svc.iniciar(machine_id, file.filename or "importado.csv", contenido)
    except maq_svc.MaquinaNoEncontrada:
        raise HTTPException(404, f"No existe la máquina '{machine_id}'")
    except svc.ImportacionError as e:
        raise HTTPException(400, str(e))


class HojaIn(BaseModel):
    import_id: str
    hoja: str


@router.post("/hoja")
def hoja(machine_id: str, body: HojaIn):
    try:
        return svc.elegir_hoja(body.import_id, body.hoja)
    except KeyError as e:
        raise HTTPException(404, str(e))
    except svc.ImportacionError as e:
        raise HTTPException(400, str(e))


class MappingIn(BaseModel):
    import_id: str
    mapeo: dict[str, str]


@router.post("/mapping")
def mapping(machine_id: str, body: MappingIn):
    try:
        return svc.mapear(body.import_id, body.mapeo)
    except KeyError as e:
        raise HTTPException(404, str(e))
    except svc.ImportacionError as e:
        raise HTTPException(400, str(e))


class ApplyIn(BaseModel):
    import_id: str
    diffs: list[str] = []
    nuevos: list[str] = []
    obsoletos: list[str] = []
    hash_esperado: str | None = None


@router.post("/apply")
def apply(machine_id: str, body: ApplyIn):
    try:
        return svc.aplicar(body.import_id, body.diffs, body.nuevos, body.obsoletos,
                           body.hash_esperado)
    except KeyError as e:
        raise HTTPException(404, str(e))
    except svc.ImportacionError as e:
        raise HTTPException(400, str(e))
    except maq_svc.ConflictoEdicionExterna as e:
        raise HTTPException(409, str(e))
