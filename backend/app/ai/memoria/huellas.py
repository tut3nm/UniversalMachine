"""
Huella: resumen estructural de los archivos de una pantalla, sin IA y sin
datos (valores de mediciones, filas del listado) — solo forma. Sirve para
buscar en la memoria de formatos (almacen.py). Ver PLAN_MEMORIA_FORMATOS.md,
secciones 3 y 5.

Una funcion de huella y una de similitud por pantalla (los datos que necesita
cada una son distintos - lineas del archivo en mediciones, plantilla parseada
+ encabezados del listado en plantilla, contexto de recetas en recetas por
area -, asi que asistente_service.py llama a la funcion de la pantalla
directamente en vez de por un despachador generico). Fases 1 a 3: mediciones,
plantilla y recetas por area (PLAN_MEMORIA_FORMATOS.md, seccion 9).
"""
from __future__ import annotations

from app.ai import tablas_delimitadas as td
from app.ai.dsl.interprete import ContextoRecetas
from app.ai.plantillas_masivas import CampoVariable, PlantillaParseada, _normalizar, _quitar_comentario

UMBRAL_SIMILITUD = 0.8


def _similitud_por_conjuntos(a: dict | None, b: dict | None, *claves: str) -> float:
    """Jaccard sobre la union de una o mas claves de la huella (cada una una
    lista de strings). Compartido por plantilla y recetas por area: mismo
    criterio, distintas claves (PLAN_MEMORIA_FORMATOS.md, seccion 6)."""
    if a is None or b is None:
        return 0.0
    conjunto_a: set[str] = set().union(*(a[c] for c in claves))
    conjunto_b: set[str] = set().union(*(b[c] for c in claves))
    if not conjunto_a and not conjunto_b:
        return 1.0
    union = conjunto_a | conjunto_b
    return len(conjunto_a & conjunto_b) / len(union) if union else 0.0


def huella_mediciones(lineas: list[str]) -> dict | None:
    """Separador + secuencia de titulos de bloque + forma de cada bloque
    (listado de 2 columnas / tabla de N columnas + primeros nombres de
    columna). None si el archivo no tiene la forma que este motor reconoce."""
    sep = td.detectar_separador(lineas)
    if sep is None:
        return None
    defs = td.detectar_tablas(lineas, sep)
    if not defs:
        return None
    try:
        resultado = td.leer_tablas(lineas, sep, defs)
    except ValueError:
        return None
    return {
        "separador": sep,
        "bloques": [
            {
                "titulo": t.titulo,
                "tipo": "tabla" if t.con_encabezado else "listado",
                "columnas": t.columnas[:8] if t.con_encabezado else [],
            }
            for t in resultado.tablas
        ],
    }


def similitud_mediciones(a: dict | None, b: dict | None) -> float:
    """Jaccard sobre los titulos de bloque, con el separador y la cantidad y
    tipo de bloques (en el mismo orden) como condicion necesaria: dos
    archivos con distinta forma de bloques nunca son el mismo formato,
    aunque compartan algunos titulos."""
    if a is None or b is None:
        return 0.0
    if a["separador"] != b["separador"]:
        return 0.0
    if len(a["bloques"]) != len(b["bloques"]):
        return 0.0
    if [x["tipo"] for x in a["bloques"]] != [x["tipo"] for x in b["bloques"]]:
        return 0.0
    titulos_a = {x["titulo"] for x in a["bloques"] if x["titulo"]}
    titulos_b = {x["titulo"] for x in b["bloques"] if x["titulo"]}
    if not titulos_a and not titulos_b:
        return 1.0
    union = titulos_a | titulos_b
    if not union:
        return 0.0
    return len(titulos_a & titulos_b) / len(union)


def prefijo_campo(plantilla: PlantillaParseada, campo: CampoVariable) -> str:
    """Texto fijo de la linea antes del {...} (sin la nota '//'): identifica
    QUE representa el campo (ej. '#Codigo;') mejor que su numero de linea,
    que cambia de una plantilla a otra de la misma familia."""
    sin_comentario = _quitar_comentario(plantilla.lineas[campo.linea_index])
    idx = sin_comentario.find("{")
    return (sin_comentario[:idx] if idx != -1 else sin_comentario).strip()


def huella_plantilla(plantilla: PlantillaParseada, encabezados: list[str]) -> dict | None:
    """Conjunto de campos {...} de la plantilla (por su prefijo) + encabezados
    del listado. None si la plantilla no tiene ningun campo variable."""
    if not plantilla.campos:
        return None
    return {
        "campos": sorted({prefijo_campo(plantilla, c) for c in plantilla.campos}),
        "encabezados": sorted(encabezados),
    }


def similitud_plantilla(a: dict | None, b: dict | None) -> float:
    """Jaccard sobre la union de campos y encabezados: PLAN_MEMORIA_FORMATOS.md,
    seccion 6."""
    return _similitud_por_conjuntos(a, b, "campos", "encabezados")


def huella_recetas(ctx: ContextoRecetas) -> dict | None:
    """Encabezados del listado (normalizados) + areas presentes. None si el
    listado no tiene encabezados (no deberia pasar: ContextoRecetas siempre
    viene de un listado ya parseado)."""
    if not ctx.encabezados:
        return None
    areas = {_normalizar(f.get(ctx.col_area, "")) for f in ctx.filas}
    return {
        "encabezados": sorted(_normalizar(h) for h in ctx.encabezados),
        "areas": sorted(a for a in areas if a),
    }


def similitud_recetas(a: dict | None, b: dict | None) -> float:
    """Jaccard sobre la union de encabezados y areas: PLAN_MEMORIA_FORMATOS.md,
    seccion 6."""
    return _similitud_por_conjuntos(a, b, "encabezados", "areas")
