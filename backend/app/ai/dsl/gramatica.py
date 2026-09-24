"""
Gramaticas GBNF de la etapa de parametros, una por pantalla (ver
PLAN_ASISTENTE_IA.md, secciones 3.3 y 12). Cada una admite solo las
operaciones de su pantalla, y los literales (columnas, sufijos, lineas de
plantilla, separadores) salen de los archivos que esa pantalla tiene
cargados: un encabezado que el listado no tiene queda fuera del alfabeto de
la gramatica, no es que el modelo "elija bien" (mismo principio que
build_labeling_grammar en app/ai/llm.py).
"""
from __future__ import annotations

import json

from app.ai.llm import _gbnf_escape
from app.ai.tablas_delimitadas import SEPARADORES

_MAX_TABLAS = 10
_MAX_OPERACIONES = 8
_MAX_VALORES_FILTRO = 200
_MAX_SLOTS_NOMBRE = 3


def _alternativas_literal(valores: list[str]) -> str:
    return " | ".join(f'"\\"{_gbnf_escape(v)}\\""' for v in valores)


def _alternativas_json(valores: list) -> str:
    """Cada valor como el literal JSON exacto que el modelo tiene que emitir."""
    return " | ".join(f'"{_gbnf_escape(json.dumps(v, ensure_ascii=False))}"' for v in valores)


def _reglas_filtro(valores_por_columna: dict[str, list[str]]) -> list[str]:
    """op-filtrar con una alternativa por columna, y el valor restringido a
    los valores que esa columna realmente tiene en el listado. Una columna
    con demasiados valores distintos no se ofrece para filtrar."""
    alternativas, reglas = [], []
    for i, (columna, valores) in enumerate(valores_por_columna.items()):
        distintos = sorted({v.strip() for v in valores if v.strip()})
        if not distintos or len(distintos) > _MAX_VALORES_FILTRO:
            continue
        alternativas.append(
            '"{\\"op\\": \\"filtrar_filas\\", \\"args\\": {\\"columna\\": '
            f'{_gbnf_escape(json.dumps(columna, ensure_ascii=False))}, \\"valor\\": " valor-{i} "}}}}"'
        )
        reglas.append(f"valor-{i} ::= {_alternativas_json(distintos)}")
    if not alternativas:
        return []
    return [f"op-filtrar ::= {' | '.join(alternativas)}", *reglas]


def gramatica_recetas(
    columnas: list[str],
    sufijos: list[str],
    valores_por_columna: dict[str, list[str]],
    slots_nombre: list[str],
    campos: list[str],
    quitar_comentarios: bool,
    agrupar: bool,
    nombrar: bool,
) -> str:
    """Array de operaciones finas (posiblemente vacio) para ajustar la
    generacion de recetas por area. Todo lo que recibe ya viene filtrado a
    lo que el mensaje del usuario menciona (planificador.py): una operacion
    sin nada mencionado que la alimente no es emitible. El patron de nombre
    solo admite esos {slots}, siempre con {sufijo}, caracteres validos para
    un nombre de archivo y un largo acotado."""
    filtro = _reglas_filtro(valores_por_columna)
    slots = " | ".join(f'"{{{_gbnf_escape(s)}}}"' for s in slots_nombre)
    operaciones: list[str] = []
    reglas: list[str] = [*filtro]
    if filtro:
        operaciones.append("op-filtrar")
    if columnas and campos:
        operaciones.append("op-reemplazar")
        reglas += [
            (
                'op-reemplazar ::= "{\\"op\\": \\"reemplazar_campo\\", \\"args\\": {\\"campo\\": " '
                'campo ", \\"columna\\": " columna "}}"'
            ),
            f"campo ::= {_alternativas_literal(campos)}",
        ]
    if slots and nombrar:
        operaciones.append("op-nombrar")
        reglas += [
            (
                'op-nombrar ::= "{\\"op\\": \\"nombrar_archivo\\", \\"args\\": {\\"patron\\": " '
                'patron "}}"'
            ),
            # una o mas columnas, {sufijo} y la extension de las recetas: sin
            # letras libres, el modelo no puede deletrear una columna a mano
            f'patron ::= "\\"" (slot-nombre separador-nombre){{1,{_MAX_SLOTS_NOMBRE}}} "{{sufijo}}.def.txt\\""',
            f"slot-nombre ::= {slots}",
            'separador-nombre ::= "." | "_" | "-"',
        ]
    if columnas and agrupar:
        operaciones.append("op-agrupar")
        reglas.append(
            'op-agrupar ::= "{\\"op\\": \\"agrupar_salida_por\\", \\"args\\": {\\"columna\\": " '
            'columna "}}"'
        )
    if "op-reemplazar" in operaciones or "op-agrupar" in operaciones:
        reglas.append(f"columna ::= {_alternativas_literal(columnas)}")
    if quitar_comentarios:
        operaciones.append("op-quitar")
        reglas.append('op-quitar ::= "{\\"op\\": \\"quitar_comentarios\\", \\"args\\": {}}"')

    # expandir_por_catalogo sin sufijos es el default que agrega el
    # planificador. Si el mensaje nombra sufijos, restringir a ellos es
    # obligatorio, una sola vez y en primer lugar.
    expandir = []
    if sufijos:
        expandir = [
            (
                'op-expandir ::= "{\\"op\\": \\"expandir_por_catalogo\\", \\"args\\": {\\"solo_sufijos\\": [" '
                f'sufijo ("," sufijo){{0,{len(sufijos) - 1}}} "]}}}}"'
            ),
            f"sufijo ::= {_alternativas_literal(sufijos)}",
        ]
    resto = f'("," operacion){{0,{_MAX_OPERACIONES - 1}}}'
    if operaciones and expandir:
        root = f'root ::= "[" op-expandir {resto} "]"'
    elif operaciones:
        root = f'root ::= "[]" | "[" operacion {resto} "]"'
    elif expandir:
        root = 'root ::= "[" op-expandir "]"'
    else:
        return 'root ::= "[]"\n'
    return "\n".join([
        root,
        *([f"operacion ::= {' | '.join(operaciones)}"] if operaciones else []),
        *expandir,
        *reglas,
        "",
    ])


def gramatica_mediciones(rangos: list[tuple[int, int]]) -> str:
    """definir_tablas y usar_separador. Los rangos (desde, hasta) de cada
    tabla ya vienen fijados por lo que el usuario escribio (planificador.py,
    rangos_mencionados): el modelo solo elige, por cada rango, 'tipo'
    ("tabla" con encabezado o "listado" clave/valor) y cuales de los rangos
    mencionados usar. Sin rangos en el mensaje, definir_tablas no es
    emitible. El separador sale de la lista cerrada del motor."""
    reglas_tablas = []
    operaciones = ["op-separador"]
    rangos_unicos = list(dict.fromkeys(rangos))[:_MAX_TABLAS]
    if rangos_unicos:
        operaciones.insert(0, "op-tablas")
        alternativas_tabla = " | ".join(
            f'"{{\\"desde\\": {desde}, \\"hasta\\": {hasta}, \\"tipo\\": " tipo "}}"'
            for desde, hasta in rangos_unicos
        )
        reglas_tablas = [
            (
                'op-tablas ::= "{\\"op\\": \\"definir_tablas\\", \\"args\\": {\\"tablas\\": [" '
                f'tabla ("," tabla){{0,{len(rangos_unicos) - 1}}} "]}}}}"'
            ),
            f"tabla ::= {alternativas_tabla}",
            'tipo ::= "\\"tabla\\"" | "\\"listado\\""',
        ]
    return "\n".join([
        'root ::= "[]" | "[" operacion ("," operacion)? "]"',
        f"operacion ::= {' | '.join(operaciones)}",
        *reglas_tablas,
        (
            'op-separador ::= "{\\"op\\": \\"usar_separador\\", \\"args\\": {\\"separador\\": " '
            'separador "}}"'
        ),
        f"separador ::= {_alternativas_json(list(SEPARADORES))}",
        "",
    ])


def gramatica_plantilla(
    lineas: list[int],
    columnas: list[str],
    valores_por_columna: dict[str, list[str]],
    nombre_archivo: bool,
) -> str:
    """Igual que en recetas, todo viene filtrado a lo que el mensaje
    menciona: lineas de la plantilla (por sus palabras, ej. 'codigo' ->
    '#Codigo;{...}'), columnas del listado y valores de filtro.
    nombre_archivo_desde solo si el mensaje habla del nombre del archivo."""
    operaciones: list[str] = []
    reglas: list[str] = []
    if lineas and columnas:
        operaciones.append("op-asignar")
        reglas += [
            (
                'op-asignar ::= "{\\"op\\": \\"asignar_columna\\", \\"args\\": {\\"linea\\": " '
                'linea ", \\"columna\\": " columna "}}"'
            ),
            "linea ::= " + " | ".join(f'"{n}"' for n in lineas),
        ]
    if nombre_archivo and columnas:
        operaciones.append("op-nombre")
        reglas.append(
            'op-nombre ::= "{\\"op\\": \\"nombre_archivo_desde\\", \\"args\\": {\\"columna\\": " '
            'columna "}}"'
        )
    if columnas and (lineas or nombre_archivo):
        reglas.append(f"columna ::= {_alternativas_json(columnas)}")
    filtro = _reglas_filtro(valores_por_columna)
    if filtro:
        operaciones.append("op-filtrar")
        reglas += filtro
    if not operaciones:
        return 'root ::= "[]"\n'
    return "\n".join([
        f'root ::= "[]" | "[" operacion ("," operacion){{0,{_MAX_OPERACIONES - 1}}} "]"',
        f"operacion ::= {' | '.join(operaciones)}",
        *reglas,
        "",
    ])
