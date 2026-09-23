"""
Orquesta: contexto de pantalla + texto libre del usuario -> Programa.

Dos llamadas al modelo, cada una bajo su propia gramatica GBNF (ver
gramatica.py): primero la intencion (que pantalla/operacion gruesa), despues
- solo si la intencion es 'generar_recetas_por_area' y hay un contexto de
recetas disponible - los ajustes finos opcionales. Cualquier otra intencion
gruesa se devuelve como programa de una sola operacion: su ejecucion real
(con los archivos que haga falta subir ademas del listado) es responsabilidad
del endpoint, no de este modulo (ver PLAN_ASISTENTE_IA.md seccion 3.5).

Si el modelo no esta disponible o responde algo no interpretable, se
devuelve un Programa 'desconocido' en vez de adivinar: es la salida digna
que describe la seccion 3.3 del plan.
"""
from __future__ import annotations

from typing import Callable, Optional

from app.ai import llm
from app.ai.dsl import gramatica
from app.ai.dsl.interprete import ContextoRecetas, Operacion, Programa
from app.ai.dsl.operaciones import OPERACION_DESCONOCIDO, TODAS, nombres_gruesas


def _system_intencion(operaciones_disponibles: list[str]) -> str:
    lineas = [
        f"- {nombre}: {TODAS[nombre].descripcion}" for nombre in operaciones_disponibles
    ]
    return (
        "Sos un clasificador. Estas son las operaciones posibles:\n"
        + "\n".join(lineas)
        + "\nElegis la que mejor describe el pedido del usuario, o 'desconocido' "
        "si ninguna aplica claramente. Respondes solo el JSON pedido, nada mas."
    )

SYSTEM_PARAMETROS = (
    "Sos un asistente que ajusta la generacion de recetas por area. A partir "
    "del pedido del usuario, elegis que operaciones finas aplicar (puede ser "
    "ninguna). Respondes solo el JSON pedido, nada mas."
)

EjecutorLlm = Callable[..., llm.LlmResult]


def _programa_desconocido() -> Programa:
    return Programa(operaciones=(Operacion(OPERACION_DESCONOCIDO, {}),))


def _elegir_intencion(
    texto: str, ejecutar_llm: EjecutorLlm, operaciones_disponibles: Optional[list[str]] = None
) -> Optional[str]:
    operaciones_disponibles = list(operaciones_disponibles or nombres_gruesas())
    g = gramatica.gramatica_intencion(operaciones_disponibles)
    resultado = ejecutar_llm(
        _system_intencion(operaciones_disponibles), texto, grammar=g, max_tokens=32
    )
    if not resultado.ok:
        return None
    datos = llm.extract_json(resultado.text)
    if not isinstance(datos, dict):
        return None
    operacion = datos.get("operacion")
    if operacion not in operaciones_disponibles and operacion != OPERACION_DESCONOCIDO:
        return None
    return operacion


def _elegir_finas(
    texto: str, ejecutar_llm: EjecutorLlm, ctx: ContextoRecetas
) -> list[Operacion]:
    sufijos = sorted({v.sufijo for catalogo in ctx.catalogos.values() for v in catalogo.variantes})
    g = gramatica.gramatica_parametros(ctx.encabezados, sufijos)
    resultado = ejecutar_llm(SYSTEM_PARAMETROS, texto, grammar=g, max_tokens=256)
    if not resultado.ok:
        return []
    datos = llm.extract_json(resultado.text)
    if not isinstance(datos, list):
        return []
    finas = []
    for item in datos:
        if isinstance(item, dict) and isinstance(item.get("op"), str):
            finas.append(Operacion(item["op"], item.get("args") or {}))
    return finas


def planificar(
    texto: str,
    ctx_recetas: Optional[ContextoRecetas] = None,
    ejecutar_llm: EjecutorLlm = llm.run_llm_auto,
) -> Programa:
    """Punto de entrada del planificador. `ctx_recetas` es None cuando la
    pantalla que pide el plan no tiene todavia un listado cargado (ej. el
    usuario escribio antes de subir el archivo): en ese caso solo se resuelve
    la intencion, sin ajustes finos."""
    intencion = _elegir_intencion(texto, ejecutar_llm)
    if intencion is None or intencion == OPERACION_DESCONOCIDO:
        return _programa_desconocido()

    if intencion != "generar_recetas_por_area" or ctx_recetas is None:
        return Programa(operaciones=(Operacion(intencion, {}),))

    finas = _elegir_finas(texto, ejecutar_llm, ctx_recetas)
    operaciones = list(finas)
    if not any(o.op == "expandir_por_catalogo" for o in operaciones):
        # 'generar_recetas_por_area' siempre expande; si el ajuste fino del
        # usuario no lo menciono explicitamente (ej. solo pidio un
        # nombrar_archivo distinto), se agrega el default al principio.
        operaciones.insert(0, Operacion("expandir_por_catalogo", {}))

    return Programa(operaciones=tuple(operaciones))
