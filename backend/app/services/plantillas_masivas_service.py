"""
Servicio para el generador masivo de archivos (plantilla + listado -> N
archivos). Ver PLAN_GENERADOR_RECETAS.md. Sin persistencia de sesion: cada
llamada recibe los dos archivos completos y devuelve el resultado (reporte o
zip) en el momento, no hace falta guardar estado entre pasos.
"""
from __future__ import annotations

import io
import zipfile

from app.ai.plantillas_masivas import (
    PlantillaParseada,
    ResultadoGeneracion,
    generar,
    leer_listado,
    parsear_plantilla,
)

_EXTENSIONES_PLANTILLA_SOPORTADAS = ("txt", "csv")


class PlantillasMasivasError(ValueError):
    """Error de validacion de negocio (plantilla/listado invalidos)."""


def _decode(raw: bytes) -> str:
    for enc in ("utf-8-sig", "cp1252", "latin-1"):
        try:
            return raw.decode(enc)
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", errors="replace")


def _extension(nombre_archivo: str) -> str:
    return nombre_archivo.lower().rsplit(".", 1)[-1] if "." in nombre_archivo else ""


def cargar(
    plantilla_contenido: bytes, plantilla_nombre: str,
    listado_contenido: bytes, listado_nombre: str,
) -> tuple[PlantillaParseada, list[str], list[dict]]:
    ext = _extension(plantilla_nombre)
    if ext not in _EXTENSIONES_PLANTILLA_SOPORTADAS:
        raise PlantillasMasivasError(
            f"Tipo de plantilla no soportado todavia (.{ext}). "
            "La v1 solo soporta plantillas .txt/.csv."
        )

    plantilla = parsear_plantilla(_decode(plantilla_contenido), extension=ext)
    if not plantilla.campos:
        raise PlantillasMasivasError(
            "La plantilla no tiene ningun campo variable marcado con {...}."
        )

    try:
        encabezados, filas = leer_listado(listado_contenido, listado_nombre)
    except ValueError as e:
        raise PlantillasMasivasError(str(e)) from e

    if not filas:
        raise PlantillasMasivasError("El listado no tiene filas de datos.")
    return plantilla, encabezados, filas


def _generar_resultado(
    plantilla_contenido: bytes, plantilla_nombre: str,
    listado_contenido: bytes, listado_nombre: str,
) -> ResultadoGeneracion:
    plantilla, encabezados, filas = cargar(
        plantilla_contenido, plantilla_nombre, listado_contenido, listado_nombre
    )
    try:
        return generar(plantilla, encabezados, filas)
    except ValueError as e:
        raise PlantillasMasivasError(str(e)) from e


def armar_zip(resultado: ResultadoGeneracion, plantilla_nombre: str) -> tuple[bytes, str]:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for archivo in resultado.archivos:
            zf.writestr(archivo.nombre_archivo, archivo.contenido)
    nombre_base = plantilla_nombre.rsplit(".", 1)[0] if "." in plantilla_nombre else plantilla_nombre
    return buf.getvalue(), f"{nombre_base}.zip"


def previsualizar(
    plantilla_contenido: bytes, plantilla_nombre: str,
    listado_contenido: bytes, listado_nombre: str,
) -> dict:
    resultado = _generar_resultado(
        plantilla_contenido, plantilla_nombre, listado_contenido, listado_nombre
    )
    return {
        "cantidad_archivos": len(resultado.archivos),
        "nombres_archivo": [a.nombre_archivo for a in resultado.archivos],
        "lineas_ignoradas": resultado.lineas_ignoradas,
        "columnas_sin_uso": resultado.columnas_sin_uso,
    }


def generar_zip(
    plantilla_contenido: bytes, plantilla_nombre: str,
    listado_contenido: bytes, listado_nombre: str,
) -> tuple[bytes, str]:
    resultado = _generar_resultado(
        plantilla_contenido, plantilla_nombre, listado_contenido, listado_nombre
    )
    return armar_zip(resultado, plantilla_nombre)
