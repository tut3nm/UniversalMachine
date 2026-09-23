"""
Servicio del asistente embebido. Interpreta un pedido en lenguaje natural
(+ opcionalmente el listado ya subido) en un Programa DSL, y ejecuta un
programa contra el mundo "recetas por area" produciendo el mismo .zip que
/api/recetas-por-area/generar. Ver PLAN_ASISTENTE_IA.md.
"""
from __future__ import annotations

import io
import zipfile
from pathlib import Path

from app.ai import validacion_recetas
from app.ai.dsl import log as dsl_log
from app.ai.dsl.interprete import (
    CatalogoArea,
    Operacion,
    Programa,
    construir_contexto,
    ejecutar_programa,
    validar_programa,
)
from app.ai.dsl.operaciones import TODAS, nombres_gruesas
from app.ai.dsl.planificador import planificar
from app.ai.plantillas_masivas import _normalizar, leer_listado
from app.ai.recetas_por_area import cargar_catalogo

_AREAS = {"HD": "RecetasHD", "GPS1": "RecetasGPS1", "GPS2": "RecetasGPS2"}

_OPERACION_RECETAS = "generar_recetas_por_area"


class AsistenteError(ValueError):
    """Error de validacion de negocio (texto, listado o programa invalido)."""


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
        raise AsistenteError(f"No se pudieron cargar las plantillas de referencia: {e}") from e


def _serializar_programa(programa: Programa) -> list[dict]:
    return [{"op": o.op, "args": o.args} for o in programa.operaciones]


def _serializar_hallazgos(hallazgos: list[validacion_recetas.Hallazgo]) -> list[dict]:
    return [{"regla": h.regla, "archivo": h.archivo, "mensaje": h.mensaje} for h in hallazgos]


def _programa_desde_json(data) -> Programa:
    if not isinstance(data, list):
        raise AsistenteError("El programa debe ser una lista de operaciones.")
    operaciones = []
    for item in data:
        if not isinstance(item, dict) or not isinstance(item.get("op"), str):
            raise AsistenteError("Cada operacion debe tener 'op' (string) y 'args' (objeto).")
        operaciones.append(Operacion(item["op"], item.get("args") or {}))
    return Programa(operaciones=tuple(operaciones))


def _contexto_recetas_o_none(listado_contenido: bytes | None, listado_nombre: str | None):
    if listado_contenido is None:
        return None
    catalogos = _cargar_catalogos()
    try:
        encabezados, filas = leer_listado(listado_contenido, listado_nombre or "listado.txt")
    except ValueError as e:
        raise AsistenteError(str(e)) from e
    if not filas:
        return None
    try:
        return construir_contexto(catalogos, encabezados, filas)
    except ValueError:
        # el listado no tiene las 3 columnas que el mundo recetas necesita
        # (sellado/amortiguador/area): se interpreta sin ajustes finos, el
        # slot queda para completar a mano en la tarjeta.
        return None


def interpretar(
    texto: str,
    listado_contenido: bytes | None,
    listado_nombre: str | None,
    ejecutar_llm=None,
) -> dict:
    """Etapa que arma la PlanCard: no ejecuta nada, solo devuelve el
    programa propuesto + lo que el front necesita para mostrarlo.

    `ejecutar_llm` es solo para tests (inyectar un stub en vez del server
    real); en produccion siempre se usa el default de planificar()."""
    ctx = _contexto_recetas_o_none(listado_contenido, listado_nombre)
    kwargs = {"ejecutar_llm": ejecutar_llm} if ejecutar_llm is not None else {}
    programa = planificar(texto, ctx_recetas=ctx, **kwargs)

    resumen: dict = {"programa": _serializar_programa(programa), "desconocido": programa.es_desconocido}

    if programa.es_desconocido:
        resumen["mensaje"] = (
            "No pude identificar una tarea conocida en el pedido. Elegi una "
            "tarjeta o completa los datos a mano."
        )
        return resumen

    primera_op = programa.operaciones[0].op

    if primera_op in nombres_gruesas() and primera_op != _OPERACION_RECETAS:
        # 'generar_desde_plantilla' y 'tabular_mediciones' necesitan archivos
        # (la plantilla, el archivo de mediciones) que esta llamada no tiene
        # por que traer: el front dispara la pantalla correspondiente.
        resumen["descripcion"] = TODAS[primera_op].descripcion
        resumen["requiere_pantalla"] = primera_op
        return resumen

    # a esta altura el programa siempre es del mundo recetas (una operacion
    # gruesa 'generar_recetas_por_area', ya traducida por planificar() a sus
    # operaciones finas equivalentes).
    resumen["descripcion"] = TODAS[_OPERACION_RECETAS].descripcion

    if ctx is None:
        resumen["requiere_listado"] = True
        return resumen

    try:
        validar_programa(programa, ctx)
        vista_previa = ejecutar_programa(programa, ctx)
    except ValueError as e:
        resumen["error_validacion"] = str(e)
        return resumen

    resumen["cantidad_archivos"] = len(vista_previa.archivos)
    resumen["advertencias"] = vista_previa.advertencias

    hallazgos_listado = validacion_recetas.validar_listado(
        ctx.filas, ctx.col_sellado, ctx.col_amortiguador, ctx.col_area
    )
    areas_generadas = {a.area for a in vista_previa.archivos}
    hallazgos_catalogo: list[validacion_recetas.Hallazgo] = []
    for area in areas_generadas:
        carpeta = _AREAS.get(area)
        if carpeta is not None:
            hallazgos_catalogo.extend(validacion_recetas.auditar_carpeta(_repo_root() / "docs" / "Recetas" / carpeta))
    resumen["hallazgos"] = _serializar_hallazgos(hallazgos_listado + hallazgos_catalogo)
    return resumen


def ejecutar(
    programa_data,
    listado_contenido: bytes,
    listado_nombre: str,
    texto_usuario: str = "",
) -> tuple[bytes, str, dict]:
    """Ejecuta un programa (ya revisado/editado por el usuario en la
    PlanCard) y devuelve el .zip, igual que /api/recetas-por-area/generar."""
    programa = _programa_desde_json(programa_data)
    catalogos = _cargar_catalogos()
    try:
        encabezados, filas = leer_listado(listado_contenido, listado_nombre)
    except ValueError as e:
        raise AsistenteError(str(e)) from e
    if not filas:
        raise AsistenteError("El listado no tiene filas de datos.")

    try:
        ctx = construir_contexto(catalogos, encabezados, filas)
        resultado = ejecutar_programa(programa, ctx)
    except ValueError as e:
        raise AsistenteError(str(e)) from e

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for archivo in resultado.archivos:
            carpeta = archivo.carpeta or archivo.area
            ruta = f"{carpeta}/{archivo.nombre_archivo}" if carpeta else archivo.nombre_archivo
            zf.writestr(ruta, archivo.contenido)

    nombre_base = listado_nombre.rsplit(".", 1)[0] if "." in listado_nombre else listado_nombre
    nombre_zip = f"{nombre_base}_asistente.zip"

    dsl_log.registrar_ejecucion(
        operacion=_OPERACION_RECETAS,
        programa=_serializar_programa(programa),
        cantidad_archivos=len(resultado.archivos),
        texto_usuario=texto_usuario,
    )

    resumen = {"cantidad_archivos": len(resultado.archivos), "advertencias": resultado.advertencias}
    return buf.getvalue(), nombre_zip, resumen
