"""
Genera gramaticas GBNF para las dos etapas del planificador (ver
PLAN_ASISTENTE_IA.md seccion 3.3):

1. gramatica_intencion(): enum cerrado de operaciones gruesas + "desconocido".
2. gramatica_parametros(): el array de operaciones finas, donde los literales
   de columna/sufijo/campo estan restringidos a lo que el CONTEXTO REAL
   tiene. Un encabezado que el listado subido no tiene, o un sufijo que el
   catalogo del area no tiene, quedan fuera del alfabeto de la gramatica: no
   es que el modelo "elija bien", es que la salida no puede ser otra cosa
   (mismo principio que build_labeling_grammar en app/ai/llm.py).
"""
from __future__ import annotations

from app.ai.dsl.operaciones import CAMPOS_RECETA, OPERACION_DESCONOCIDO, nombres_gruesas
from app.ai.llm import _gbnf_escape


def _alternativas_literal(valores: list[str]) -> str:
    return " | ".join(f'"\\"{_gbnf_escape(v)}\\""' for v in valores)


def gramatica_intencion(operaciones_disponibles: list[str] | None = None) -> str:
    """Etapa 1: {"operacion": "<una de las gruesas>" | "desconocido"}."""
    opciones = list(operaciones_disponibles or nombres_gruesas()) + [OPERACION_DESCONOCIDO]
    return (
        'root ::= "{\\"operacion\\": " intencion "}"\n'
        f"intencion ::= {_alternativas_literal(opciones)}\n"
    )


def gramatica_parametros(encabezados: list[str], sufijos_disponibles: list[str]) -> str:
    """Etapa 2: un array de operaciones finas (posiblemente vacio) para
    ajustar la operacion gruesa 'generar_recetas_por_area'. Columnas y
    sufijos solo pueden ser los que el listado/catalogo realmente tienen."""
    columnas = _alternativas_literal(encabezados) if encabezados else '"\\"\\""'
    sufijos = _alternativas_literal(sufijos_disponibles) if sufijos_disponibles else '"\\"\\""'
    campos = _alternativas_literal(list(CAMPOS_RECETA))

    return "\n".join([
        'root ::= "[]" | "[" operacion ("," operacion)* "]"',
        "operacion ::= op_filtrar | op_expandir | op_reemplazar | op_nombrar | op_agrupar | op_quitar",
        (
            'op_filtrar ::= "{\\"op\\": \\"filtrar_filas\\", \\"args\\": {\\"columna\\": " '
            'columna ", \\"valor\\": " texto "}}"'
        ),
        (
            'op_expandir ::= "{\\"op\\": \\"expandir_por_catalogo\\", \\"args\\": {\\"solo_sufijos\\": " '
            'lista_sufijos "}}"'
        ),
        (
            'op_reemplazar ::= "{\\"op\\": \\"reemplazar_campo\\", \\"args\\": {\\"campo\\": " '
            'campo ", \\"columna\\": " columna "}}"'
        ),
        (
            'op_nombrar ::= "{\\"op\\": \\"nombrar_archivo\\", \\"args\\": {\\"patron\\": " '
            'texto "}}"'
        ),
        (
            'op_agrupar ::= "{\\"op\\": \\"agrupar_salida_por\\", \\"args\\": {\\"columna\\": " '
            'columna "}}"'
        ),
        'op_quitar ::= "{\\"op\\": \\"quitar_comentarios\\", \\"args\\": {}}"',
        f"columna ::= {columnas}",
        f"campo ::= {campos}",
        'lista_sufijos ::= "[]" | "[" sufijo ("," sufijo)* "]"',
        f"sufijo ::= {sufijos}",
        'texto ::= "\\"" caracter{0,64} "\\""',
        'caracter ::= [^"\\\\\\n]',
        "",
    ])
