"""
Servicio del generador de recetas por area. Ver PLAN_GENERADOR_RECETAS.md.
A diferencia de plantillas_masivas_service.py, aca el usuario solo sube el
listado: las plantillas de referencia (una por sufijo de operacion, por
area) viven en el repo, en docs/Recetas/Recetas<AREA>/, y se leen frescas en
cada llamada (son pocos archivos chicos, no hace falta cachear).
"""
from __future__ import annotations

import io
import zipfile
from pathlib import Path

from app.ai import validacion_recetas
from app.ai.plantillas_masivas import _normalizar, leer_listado
from app.ai.recetas_por_area import (
    CatalogoArea,
    ResultadoGeneracionArea,
    _buscar_columna_unica,
    cargar_catalogo,
    generar_por_area,
)

_AREAS = {"HD": "RecetasHD", "GPS1": "RecetasGPS1", "GPS2": "RecetasGPS2"}
_CARPETA_POR_AREA_NORM = {_normalizar(area): carpeta for area, carpeta in _AREAS.items()}


class RecetasPorAreaError(ValueError):
    """Error de validacion de negocio (listado invalido o catalogo incompleto)."""


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[3]


def _cargar_catalogos() -> dict[str, CatalogoArea]:
    base = _repo_root() / "docs" / "Recetas"
    try:
        return {
            _normalizar(area): cargar_catalogo(base / carpeta, area)
            for area, carpeta in _AREAS.items()
        }
    except (OSError, ValueError) as e:
        raise RecetasPorAreaError(f"No se pudieron cargar las plantillas de referencia: {e}") from e


def _generar_resultado(listado_contenido: bytes, listado_nombre: str) -> ResultadoGeneracionArea:
    catalogos = _cargar_catalogos()
    try:
        encabezados, filas = leer_listado(listado_contenido, listado_nombre)
    except ValueError as e:
        raise RecetasPorAreaError(str(e)) from e

    if not filas:
        raise RecetasPorAreaError("El listado no tiene filas de datos.")

    try:
        return generar_por_area(catalogos, encabezados, filas)
    except ValueError as e:
        raise RecetasPorAreaError(str(e)) from e


def _hallazgos_a_dict(hallazgos: list[validacion_recetas.Hallazgo]) -> list[dict]:
    return [{"regla": h.regla, "archivo": h.archivo, "mensaje": h.mensaje} for h in hallazgos]


def _hallazgos_listado(encabezados: list[str], filas: list[dict]) -> list[validacion_recetas.Hallazgo]:
    encabezados_norm = {h: _normalizar(h) for h in encabezados}
    col_sellado = _buscar_columna_unica(encabezados_norm, "sellado")
    col_amortiguador = _buscar_columna_unica(encabezados_norm, "amortiguador")
    col_area = _buscar_columna_unica(encabezados_norm, "area")
    return validacion_recetas.validar_listado(filas, col_sellado, col_amortiguador, col_area)


def _hallazgos_catalogo(areas_usadas: dict[str, int]) -> list[validacion_recetas.Hallazgo]:
    """Solo audita las areas que este listado realmente usa: si HD tiene un
    defecto conocido pero el listado es todo GPS1, no tiene sentido avisar."""
    base = _repo_root() / "docs" / "Recetas"
    hallazgos: list[validacion_recetas.Hallazgo] = []
    for area in areas_usadas:
        carpeta = _CARPETA_POR_AREA_NORM.get(_normalizar(area))
        if carpeta is None:
            continue
        hallazgos.extend(validacion_recetas.auditar_carpeta(base / carpeta))
    return hallazgos


def previsualizar(listado_contenido: bytes, listado_nombre: str) -> dict:
    catalogos = _cargar_catalogos()
    try:
        encabezados, filas = leer_listado(listado_contenido, listado_nombre)
    except ValueError as e:
        raise RecetasPorAreaError(str(e)) from e
    if not filas:
        raise RecetasPorAreaError("El listado no tiene filas de datos.")
    try:
        resultado = generar_por_area(catalogos, encabezados, filas)
    except ValueError as e:
        raise RecetasPorAreaError(str(e)) from e

    return {
        "cantidad_archivos": len(resultado.archivos),
        "areas_usadas": resultado.areas_usadas,
        "filas_sin_area": resultado.filas_sin_area,
        "nombres_archivo": [a.nombre_archivo for a in resultado.archivos],
        "hallazgos_listado": _hallazgos_a_dict(_hallazgos_listado(encabezados, filas)),
        "hallazgos_catalogo": _hallazgos_a_dict(_hallazgos_catalogo(resultado.areas_usadas)),
    }


def auditar_repositorio() -> dict:
    """Audita las plantillas de referencia de las 3 areas tal cual estan hoy
    en docs/Recetas/, sin depender de que el usuario suba nada (boton
    'Auditar recetas existentes', PLAN_ASISTENTE_IA.md seccion 5)."""
    base = _repo_root() / "docs" / "Recetas"
    hallazgos: list[validacion_recetas.Hallazgo] = []
    for area, carpeta in _AREAS.items():
        try:
            hallazgos.extend(validacion_recetas.auditar_carpeta(base / carpeta))
        except OSError as e:
            raise RecetasPorAreaError(f"No se pudo auditar el area '{area}': {e}") from e
    return {"hallazgos": _hallazgos_a_dict(hallazgos)}


def generar_zip(listado_contenido: bytes, listado_nombre: str) -> tuple[bytes, str]:
    resultado = _generar_resultado(listado_contenido, listado_nombre)

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for archivo in resultado.archivos:
            zf.writestr(f"{archivo.area}/{archivo.nombre_archivo}", archivo.contenido)

    nombre_base = listado_nombre.rsplit(".", 1)[0] if "." in listado_nombre else listado_nombre
    return buf.getvalue(), f"{nombre_base}_recetas.zip"
