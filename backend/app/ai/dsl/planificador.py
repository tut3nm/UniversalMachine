"""
Texto libre del usuario -> operaciones finas de la pantalla en la que esta.

La pantalla ya define la tarea (PLAN_ASISTENTE_IA.md, seccion 12): no hay
etapa de intencion. Una sola llamada al modelo, bajo la gramatica GBNF de esa
pantalla, traduce las indicaciones del usuario sobre SUS archivos en
operaciones. Si el mensaje no trae indicaciones, el modelo responde [] y se
usa lo que el motor detecta solo. Si el modelo no esta o devuelve algo no
interpretable, tambien se sigue con lo detectado, marcando que la IA no
respondio (nunca se adivina en silencio).
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Callable

from app.ai import llm
from app.ai import tablas_delimitadas as td
from app.ai.dsl import gramatica
from app.ai.dsl.interprete import ContextoRecetas, Operacion, _clave_slot
from app.ai.dsl.operaciones import CAMPOS_RECETA
from app.ai.plantillas_masivas import _CAMPO_RE, _normalizar

EjecutorLlm = Callable[..., llm.LlmResult]

_MAX_LINEAS_PLANTILLA_EN_PROMPT = 40

def _system_recetas(ctx: ContextoRecetas, sufijos: list[str]) -> str:
    return (
        "Traducis un pedido sobre la generacion de recetas por area a operaciones JSON. "
        "Cada fila del listado se expande en un archivo por sufijo del catalogo de su area.\n"
        f"Columnas del listado: {', '.join(ctx.encabezados)}. Sufijos: {', '.join(sufijos)}.\n"
        "- filtrar_filas: generar solo las filas donde una columna tiene un valor.\n"
        "- expandir_por_catalogo con solo_sufijos: generar solo esos sufijos.\n"
        "- reemplazar_campo: que columna llena #Codigo o #Descripcion.\n"
        "- nombrar_archivo: patron del nombre con {columna} y {sufijo}, ej. {sellado}.{sufijo}.def.txt.\n"
        "- agrupar_salida_por: carpetas del .zip segun una columna.\n"
        "- quitar_comentarios: sacar las lineas //.\n"
        "- Si el pedido no pide nada de esto, respondes [].\n"
        'Ejemplo: "solo las filas X, agrupadas por C" -> [{"op": "filtrar_filas", "args": '
        '{"columna": "<columna de X>", "valor": "X"}}, {"op": "agrupar_salida_por", "args": '
        '{"columna": "C"}}]\n'
        "Respondes solo el JSON, nada mas."
    )


def _mencionado(valor: str, texto_norm: str) -> bool:
    valor_norm = _normalizar(valor)
    return bool(valor_norm) and re.search(rf"(?<!\w){re.escape(valor_norm)}(?!\w)", texto_norm) is not None


def valores_mencionados(texto: str, encabezados: list[str], filas: list[dict]) -> dict[str, list[str]]:
    """Por columna, los valores del listado que el usuario nombro en su
    mensaje: son los unicos por los que la gramatica deja filtrar. Con un
    1.5B, ofrecerle todos los valores de todas las columnas termina en un
    filtro por cualquier columna; asi, "solo las filas GPS2" tiene una sola
    salida posible (area = GPS2)."""
    texto_norm = _normalizar(texto)
    return {
        h: sorted({f.get(h, "").strip() for f in filas if _mencionado(f.get(h, ""), texto_norm)})
        for h in encabezados
    }


def sufijos_mencionados(texto: str, sufijos: list[str]) -> list[str]:
    texto_norm = _normalizar(texto)
    return [s for s in sufijos if _mencionado(s, texto_norm)]


def columnas_mencionadas(texto: str, encabezados: list[str]) -> list[str]:
    texto_norm = _normalizar(texto)
    return [h for h in encabezados if _mencionado(h, texto_norm)]


def campos_mencionados(texto: str) -> list[str]:
    texto_norm = _normalizar(texto)
    return [c for c in CAMPOS_RECETA if _mencionado(c.lstrip("#"), texto_norm)]


def pide_quitar_comentarios(texto: str) -> bool:
    return re.search(r"coment|nota|//", _normalizar(texto)) is not None


def pide_agrupar(texto: str) -> bool:
    return re.search(r"agrup|carpeta", _normalizar(texto)) is not None


def pide_nombrar(texto: str) -> bool:
    return re.search(r"nombr|llam", _normalizar(texto)) is not None


def lineas_mencionadas(texto: str, lineas_con_campo: list[tuple[int, str]]) -> list[int]:
    """Lineas de la plantilla cuyas palabras (fuera del {valor}) aparecen en
    el mensaje: 'el codigo lo llena...' -> la linea '#Codigo;{...}'."""
    texto_norm = _normalizar(texto)
    elegidas = []
    for n, linea in lineas_con_campo:
        palabras = _PALABRA_RE.findall(_normalizar(_CAMPO_RE.sub(" ", linea)))
        por_numero = re.search(rf"\blinea\s+{n}\b", texto_norm) is not None
        if por_numero or any(_mencionado(p, texto_norm) for p in palabras):
            elegidas.append(n)
    return elegidas


def habla_del_nombre_de_archivo(texto: str) -> bool:
    return _mencionado("nombre", _normalizar(texto))


_NUMERO_RE = re.compile(r"\d+")
_PALABRA_RE = re.compile(r"[a-z]{3,}")
_RANGO_RE = re.compile(r"(\d+)\s*(?:a|-)\s*(?:la\s+)?(\d+)")
_FILA_GRUPO_RE = re.compile(r"\bfilas?\s+(\d+(?:\s*(?:y|,)\s*\d+)*)\b")


def rangos_mencionados(texto: str, total_lineas: int) -> list[tuple[int, int]]:
    """Rangos (desde, hasta) que el usuario escribio explicitamente, en el
    orden en que aparecen en el mensaje: son los unicos que la gramatica le
    deja emitir al modelo (no arma pares el mismo, solo clasifica cada uno).
    "de la fila 1 a la 41" / "de la 43 a la 53" dan un rango; numeros sueltos
    junto a la palabra "fila(s)" que no forman parte de un rango ya
    encontrado (ej. "la fila 56 y 57") dan un rango de una sola fila cada
    uno. Un rango fuera del archivo se descarta entero, sin caer a sus
    numeros sueltos."""
    texto_norm = texto.lower()
    ocupado = bytearray(len(texto_norm))
    hallados: list[tuple[int, int, int]] = []
    for m in _RANGO_RE.finditer(texto_norm):
        for i in range(m.start(), m.end()):
            ocupado[i] = 1
        a, b = int(m.group(1)), int(m.group(2))
        if 1 <= a <= total_lineas and 1 <= b <= total_lineas:
            desde, hasta = (a, b) if a <= b else (b, a)
            hallados.append((m.start(), desde, hasta))
    for m in _FILA_GRUPO_RE.finditer(texto_norm):
        for nm in _NUMERO_RE.finditer(m.group(1)):
            pos = m.start(1) + nm.start()
            if ocupado[pos]:
                continue
            n = int(nm.group())
            if 1 <= n <= total_lineas:
                hallados.append((pos, n, n))
    hallados.sort(key=lambda t: t[0])
    rangos: list[tuple[int, int]] = []
    for _, desde, hasta in hallados:
        par = (desde, hasta)
        if par not in rangos:
            rangos.append(par)
    return rangos


def _fragmento_rango(lineas: list[str], desde: int, hasta: int) -> str:
    """Primeras (hasta 2) lineas reales del rango, sin titulos de seccion:
    lo que el modelo ve para clasificar el rango como listado o tabla."""
    contenido = [l.strip() for l in lineas[desde - 1:hasta] if l.strip() and not td.es_titulo(l)]
    return " / ".join(contenido[:2]) if contenido else "(sin contenido)"


def _system_mediciones(total_lineas: int, deteccion: str, rangos: list[tuple[int, int]], lineas: list[str]) -> str:
    ejemplos = "\n".join(
        f"  filas {desde}-{hasta}: {_fragmento_rango(lineas, desde, hasta)}" for desde, hasta in rangos
    )
    return (
        "Traducis indicaciones sobre la estructura de un archivo de texto con tablas a "
        f"operaciones JSON. El archivo tiene {total_lineas} filas. Lo que se detecto "
        f"automaticamente: {deteccion}.\n"
        + (f"Rangos que el usuario mencionó, con sus primeras lineas reales:\n{ejemplos}\n" if rangos else "")
        + "- Si el usuario indica en que filas esta cada tabla, emitis definir_tablas con una "
        "entrada por cada rango de arriba (desde, hasta ya fijados). 'tipo' es \"tabla\" si esa "
        "tabla tiene una fila con los nombres de columna, o \"listado\" si son pares clave/valor "
        "(una columna con el nombre del dato y otra con el valor), segun lo que diga el usuario o "
        "se vea en las lineas de ejemplo.\n"
        "- Si indica el separador de columnas, emitis usar_separador.\n"
        "- Si no dice nada de filas ni de separador, respondes [].\n"
        'Ejemplo: "la primera tabla va de la fila A a la B, la segunda de la C a la D, '
        'separadas por punto y coma" -> [{"op": "definir_tablas", "args": {"tablas": '
        '[{"desde": A, "hasta": B, "tipo": "tabla"}, {"desde": C, "hasta": D, '
        '"tipo": "tabla"}]}}, {"op": "usar_separador", "args": {"separador": ";"}}]\n'
        "Respondes solo el JSON, nada mas."
    )


def _system_plantilla(lineas_con_campo: list[tuple[int, str]], encabezados: list[str]) -> str:
    lineas = "\n".join(
        f"  linea {n}: {texto[:60]}" for n, texto in lineas_con_campo[:_MAX_LINEAS_PLANTILLA_EN_PROMPT]
    )
    return (
        "Traducis indicaciones sobre como llenar una plantilla con un listado a operaciones JSON.\n"
        f"Lineas de la plantilla con un campo variable {{...}}:\n{lineas}\n"
        f"Columnas del listado: {', '.join(encabezados)}.\n"
        "- asignar_columna: que columna del listado llena el campo de una linea.\n"
        "- nombre_archivo_desde: de que columna sale el nombre de cada archivo.\n"
        "- filtrar_filas: generar solo las filas donde una columna tiene un valor.\n"
        "- Si el pedido no dice nada de esto, respondes [].\n"
        "Un pedido puede tener varias indicaciones: emitis una operacion por cada una.\n"
        'Ejemplo: "el X lo llena la columna A y el Y la columna B, solo las filas V" -> '
        '[{"op": "asignar_columna", "args": {"linea": <linea de X>, "columna": "A"}}, '
        '{"op": "asignar_columna", "args": {"linea": <linea de Y>, "columna": "B"}}, '
        '{"op": "filtrar_filas", "args": {"columna": "<columna de V>", "valor": "V"}}]\n'
        "Respondes solo el JSON, nada mas."
    )


@dataclass(frozen=True)
class Plan:
    operaciones: tuple[Operacion, ...]
    ia_respondio: bool


def _pedir_operaciones(
    system: str, texto: str, grammar: str, ejecutar_llm: EjecutorLlm, max_tokens: int
) -> list[Operacion] | None:
    resultado = ejecutar_llm(system, texto, grammar=grammar, max_tokens=max_tokens)
    if not resultado.ok:
        return None
    datos = llm.extract_json(resultado.text)
    if not isinstance(datos, list):
        return None
    operaciones: list[Operacion] = []
    for item in datos:
        if not isinstance(item, dict) or not isinstance(item.get("op"), str):
            continue
        operacion = Operacion(item["op"], item.get("args") or {})
        # un 1.5B a veces repite la misma operacion hasta el tope: repetirla
        # no cambia nada, se descarta
        if operacion not in operaciones:
            operaciones.append(operacion)
    return operaciones


def _plan(operaciones: list[Operacion] | None) -> Plan:
    return Plan(operaciones=tuple(operaciones or ()), ia_respondio=operaciones is not None)


def planificar_recetas(
    texto: str, ctx: ContextoRecetas, ejecutar_llm: EjecutorLlm = llm.run_llm_auto
) -> Plan:
    sufijos = sorted({v.sufijo for catalogo in ctx.catalogos.values() for v in catalogo.variantes})
    columnas = columnas_mencionadas(texto, ctx.encabezados)
    g = gramatica.gramatica_recetas(
        columnas,
        sufijos_mencionados(texto, sufijos),
        valores_mencionados(texto, ctx.encabezados, ctx.filas),
        [_clave_slot(c) for c in columnas],
        campos_mencionados(texto),
        pide_quitar_comentarios(texto),
        pide_agrupar(texto),
        pide_nombrar(texto),
    )
    operaciones = _pedir_operaciones(_system_recetas(ctx, sufijos), texto, g, ejecutar_llm, max_tokens=256)
    plan = _plan(operaciones)
    if any(o.op == "expandir_por_catalogo" for o in plan.operaciones):
        return plan
    # generar recetas por area siempre expande; si el pedido solo ajusto
    # otra cosa (ej. el nombre de archivo), se agrega el default al principio.
    return Plan(
        operaciones=(Operacion("expandir_por_catalogo", {}),) + plan.operaciones,
        ia_respondio=plan.ia_respondio,
    )


def planificar_mediciones(
    texto: str, lineas: list[str], deteccion: str, ejecutar_llm: EjecutorLlm = llm.run_llm_auto
) -> Plan:
    rangos = rangos_mencionados(texto, len(lineas))
    g = gramatica.gramatica_mediciones(rangos)
    system = _system_mediciones(len(lineas), deteccion, rangos, lineas)
    return _plan(_pedir_operaciones(system, texto, g, ejecutar_llm, max_tokens=256))


def planificar_plantilla(
    texto: str,
    lineas_con_campo: list[tuple[int, str]],
    encabezados: list[str],
    filas: list[dict],
    ejecutar_llm: EjecutorLlm = llm.run_llm_auto,
) -> Plan:
    g = gramatica.gramatica_plantilla(
        lineas_mencionadas(texto, lineas_con_campo),
        columnas_mencionadas(texto, encabezados),
        valores_mencionados(texto, encabezados, filas),
        habla_del_nombre_de_archivo(texto),
    )
    system = _system_plantilla(lineas_con_campo, encabezados)
    return _plan(_pedir_operaciones(system, texto, g, ejecutar_llm, max_tokens=384))
