"""
Anclaje: programa DSL (numeros de fila, validos solo para el archivo que se
subio) <-> regla anclada (titulos de seccion / prefijos de campo / nombres de
columna, validos para cualquier archivo del mismo formato). Ver
PLAN_MEMORIA_FORMATOS.md, secciones 5.1, 5.2 y 5.3.

anclar_*() se llama al guardar un formato: traduce el programa que el usuario
confirmo a anclas. aplicar_*() se llama al reconocer: busca en el archivo
NUEVO lo que tiene esas anclas, y devuelve sus numeros de fila reales en ESE
archivo. Una ancla que no aparece es un error explicito
(PLAN_MEMORIA_FORMATOS.md, seccion 4, paso 5): no se adivina ni se aplica a
medias.
"""
from __future__ import annotations

from dataclasses import dataclass

from app.ai import tablas_delimitadas as td
from app.ai.dsl.interprete import ContextoRecetas, Operacion, Programa, validar_programa
from app.ai.memoria.huellas import prefijo_campo
from app.ai.plantillas_masivas import PlantillaParseada

ANCLA_INICIO = "inicio de archivo"
ANCLA_LINEA_VACIA = "linea vacia"
ANCLA_FIN = "fin de archivo"


@dataclass(frozen=True)
class TablaAnclada:
    ancla_desde: str
    ancla_hasta: str
    tipo: str  # "listado" | "tabla"


@dataclass(frozen=True)
class ReglaMediciones:
    separador: str
    tablas: tuple[TablaAnclada, ...]


def regla_a_json(regla: ReglaMediciones) -> dict:
    return {
        "separador": regla.separador,
        "tablas": [
            {"ancla_desde": t.ancla_desde, "ancla_hasta": t.ancla_hasta, "tipo": t.tipo}
            for t in regla.tablas
        ],
    }


def regla_desde_json(data: dict) -> ReglaMediciones:
    return ReglaMediciones(
        separador=data["separador"],
        tablas=tuple(
            TablaAnclada(t["ancla_desde"], t["ancla_hasta"], t["tipo"]) for t in data["tablas"]
        ),
    )


def _describir_hasta(lineas: list[str], hasta: int) -> str:
    if hasta >= len(lineas):
        return ANCLA_FIN
    siguiente = lineas[hasta]  # lineas[hasta] es la linea numero hasta+1 (1-based)
    if td.es_titulo(siguiente):
        return td.texto_titulo(siguiente)
    if not siguiente.strip():
        return ANCLA_LINEA_VACIA
    return ANCLA_FIN


def _bloque_contenedor(bloques: list[td.TablaDef], desde: int, hasta: int) -> td.TablaDef | None:
    return next((d for d in bloques if d.desde <= desde and hasta <= d.hasta), None)


def anclar_mediciones(tablas: list[dict], separador: str, lineas: list[str]) -> ReglaMediciones:
    bloques = td.detectar_tablas(lineas, separador)
    ancladas = []
    for t in tablas:
        desde, hasta, tipo = t["desde"], t["hasta"], t["tipo"]
        contenedor = _bloque_contenedor(bloques, desde, hasta)
        d_desde, d_hasta = (contenedor.desde, contenedor.hasta) if contenedor else (desde, hasta)
        ancla_desde = td.titulo_para(lineas, d_desde, d_hasta) or ANCLA_INICIO
        ancla_hasta = _describir_hasta(lineas, d_hasta)
        ancladas.append(TablaAnclada(ancla_desde, ancla_hasta, tipo))
    return ReglaMediciones(separador=separador, tablas=tuple(ancladas))


def aplicar_mediciones(regla: ReglaMediciones, lineas: list[str]) -> list[dict]:
    bloques = td.detectar_tablas(lineas, regla.separador)
    usados: set[int] = set()
    tablas: list[dict] = []
    for ta in regla.tablas:
        encontrado = None
        for i, d in enumerate(bloques):
            if i in usados:
                continue
            ancla_desde = td.titulo_para(lineas, d.desde, d.hasta) or ANCLA_INICIO
            ancla_hasta = _describir_hasta(lineas, d.hasta)
            if ancla_desde == ta.ancla_desde and ancla_hasta == ta.ancla_hasta:
                encontrado = d
                usados.add(i)
                break
        if encontrado is None:
            raise ValueError(
                f"No encontre en este archivo la tabla que empieza en '{ta.ancla_desde}' "
                f"y termina en '{ta.ancla_hasta}': el formato guardado no coincide."
            )
        tablas.append({"desde": encontrado.desde, "hasta": encontrado.hasta, "tipo": ta.tipo})
    return tablas


# ---------------------------------------------------------------------------
# Plantilla (PLAN_MEMORIA_FORMATOS.md, seccion 5.2)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class AsignacionAnclada:
    prefijo_campo: str
    columna: str


@dataclass(frozen=True)
class ReglaPlantilla:
    asignaciones: tuple[AsignacionAnclada, ...]
    columna_nombre_archivo: str | None


def regla_plantilla_a_json(regla: ReglaPlantilla) -> dict:
    return {
        "asignaciones": [{"prefijo_campo": a.prefijo_campo, "columna": a.columna} for a in regla.asignaciones],
        "columna_nombre_archivo": regla.columna_nombre_archivo,
    }


def regla_plantilla_desde_json(data: dict) -> ReglaPlantilla:
    return ReglaPlantilla(
        asignaciones=tuple(
            AsignacionAnclada(a["prefijo_campo"], a["columna"]) for a in data["asignaciones"]
        ),
        columna_nombre_archivo=data.get("columna_nombre_archivo"),
    )


def anclar_plantilla(
    asignaciones: list[dict], columna_nombre_archivo: str | None, plantilla: PlantillaParseada
) -> ReglaPlantilla:
    """asignaciones: [{"linea": N, "columna": "..."}], como emite el
    programa DSL (asignar_columna). filtrar_filas no se ancla (seccion 3.1):
    depende de que quiere generar el usuario hoy, no de la forma del archivo."""
    prefijo_por_linea = {c.linea_index + 1: prefijo_campo(plantilla, c) for c in plantilla.campos}
    ancladas = []
    for a in asignaciones:
        prefijo = prefijo_por_linea.get(a["linea"])
        if prefijo is None:
            raise ValueError(f"La linea {a['linea']} no tiene ningun campo {{...}} en esta plantilla.")
        ancladas.append(AsignacionAnclada(prefijo, a["columna"]))
    return ReglaPlantilla(asignaciones=tuple(ancladas), columna_nombre_archivo=columna_nombre_archivo)


def aplicar_plantilla(
    regla: ReglaPlantilla, plantilla: PlantillaParseada, encabezados: list[str]
) -> tuple[list[dict], str | None]:
    linea_por_prefijo = {prefijo_campo(plantilla, c): c.linea_index + 1 for c in plantilla.campos}
    asignaciones = []
    for a in regla.asignaciones:
        linea = linea_por_prefijo.get(a.prefijo_campo)
        if linea is None:
            raise ValueError(
                f"No encontre en esta plantilla el campo '{a.prefijo_campo}': el formato guardado "
                "no coincide."
            )
        if a.columna not in encabezados:
            raise ValueError(f"El listado no tiene la columna '{a.columna}'.")
        asignaciones.append({"linea": linea, "columna": a.columna})
    nombre_col = regla.columna_nombre_archivo
    if nombre_col is not None and nombre_col not in encabezados:
        raise ValueError(f"El listado no tiene la columna '{nombre_col}' para el nombre del archivo.")
    return asignaciones, nombre_col


# ---------------------------------------------------------------------------
# Recetas por area (PLAN_MEMORIA_FORMATOS.md, seccion 5.3)
# ---------------------------------------------------------------------------

# Las unicas operaciones de recetas que se guardan: ya son por nombre de
# columna, no por posicion, asi que no hace falta traducirlas a un ancla
# distinta - alcanza con guardar solo estas (filtrar_filas depende de que
# quiere generar el usuario HOY, no de la forma del archivo; y
# expandir_por_catalogo siempre se vuelve a agregar sin restriccion de
# sufijos al aplicar, seccion 3.1).
_OPERACIONES_RECETAS_GUARDABLES = frozenset(
    {"reemplazar_campo", "nombrar_archivo", "agrupar_salida_por", "quitar_comentarios"}
)


@dataclass(frozen=True)
class ReglaRecetas:
    operaciones: tuple[Operacion, ...]


def regla_recetas_a_json(regla: ReglaRecetas) -> dict:
    return {"operaciones": [{"op": o.op, "args": o.args} for o in regla.operaciones]}


def regla_recetas_desde_json(data: dict) -> ReglaRecetas:
    return ReglaRecetas(
        operaciones=tuple(Operacion(o["op"], o["args"]) for o in data["operaciones"])
    )


def anclar_recetas(operaciones: list[Operacion]) -> ReglaRecetas:
    return ReglaRecetas(operaciones=tuple(
        o for o in operaciones if o.op in _OPERACIONES_RECETAS_GUARDABLES
    ))


def aplicar_recetas(regla: ReglaRecetas, ctx: ContextoRecetas) -> Programa:
    """expandir_por_catalogo (sin restriccion de sufijos) + las operaciones
    guardadas. Reusa validar_programa (interprete.py) para el chequeo de
    columna/patron ausente: mismo mensaje de error que si el usuario mismo
    hubiese escrito esa operacion contra este listado."""
    programa = Programa(
        operaciones=(Operacion("expandir_por_catalogo", {}),) + regla.operaciones
    )
    validar_programa(programa, ctx)
    return programa
