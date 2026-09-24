"""
Catalogo declarativo del DSL de operaciones del asistente embebido.

Cada pantalla con asistente tiene su propio juego de operaciones finas: la
pantalla ya define la tarea (recetas por area, mediciones, plantilla), el
asistente solo ajusta COMO se hace sobre los archivos que esa pantalla tiene
cargados (PLAN_ASISTENTE_IA.md, seccion 12). El modelo elige operaciones y
argumentos estructurales - nunca un valor que termine escrito dentro de un
archivo -, y los argumentos se validan siempre contra los archivos reales.

Regla de crecimiento (seccion 3.1 del plan): no se agrega una operacion sin
un pedido real que la haya requerido.
"""
from __future__ import annotations

from dataclasses import dataclass

# Los dos unicos campos de una plantilla de receta que varian por registro
# (ver recetas_por_area.py: VarianteArea.linea_codigo / linea_descripcion).
CAMPOS_RECETA = ("#Codigo", "#Descripcion")

PANTALLA_RECETAS = "recetas_por_area"
PANTALLA_MEDICIONES = "mediciones"
PANTALLA_PLANTILLA = "plantilla"
PANTALLAS = (PANTALLA_RECETAS, PANTALLA_MEDICIONES, PANTALLA_PLANTILLA)


@dataclass(frozen=True)
class DefinicionOperacion:
    nombre: str
    pantallas: tuple[str, ...]
    descripcion: str


_OPERACIONES: tuple[DefinicionOperacion, ...] = (
    DefinicionOperacion(
        "filtrar_filas", (PANTALLA_RECETAS, PANTALLA_PLANTILLA),
        "Recorta el listado a las filas que cumplen columna == valor.",
    ),
    DefinicionOperacion(
        "expandir_por_catalogo", (PANTALLA_RECETAS,),
        "Expande cada fila a un archivo por sufijo del catalogo de su area.",
    ),
    DefinicionOperacion(
        "reemplazar_campo", (PANTALLA_RECETAS,),
        "Cambia que columna del listado alimenta un campo (#Codigo o #Descripcion) de la plantilla.",
    ),
    DefinicionOperacion(
        "nombrar_archivo", (PANTALLA_RECETAS,),
        'Define el patron de nombre de archivo, ej. "{amortiguador}.{sufijo}.def.txt".',
    ),
    DefinicionOperacion(
        "agrupar_salida_por", (PANTALLA_RECETAS,),
        "Agrupa los archivos de salida en carpetas del .zip segun una columna.",
    ),
    DefinicionOperacion(
        "quitar_comentarios", (PANTALLA_RECETAS,),
        "Saca las lineas de nota '//' del resultado.",
    ),
    DefinicionOperacion(
        "definir_tablas", (PANTALLA_MEDICIONES,),
        "Indica las filas de cada tabla del archivo (desde, hasta, si la primera fila es encabezado).",
    ),
    DefinicionOperacion(
        "usar_separador", (PANTALLA_MEDICIONES,),
        "Indica el separador de columnas del archivo.",
    ),
    DefinicionOperacion(
        "asignar_columna", (PANTALLA_PLANTILLA,),
        "Indica que columna del listado llena el campo {...} de una linea de la plantilla.",
    ),
    DefinicionOperacion(
        "nombre_archivo_desde", (PANTALLA_PLANTILLA,),
        "Indica de que columna del listado sale el nombre de cada archivo.",
    ),
)

TODAS: dict[str, DefinicionOperacion] = {op.nombre: op for op in _OPERACIONES}


def nombres_de(pantalla: str) -> list[str]:
    return [op.nombre for op in _OPERACIONES if pantalla in op.pantallas]
