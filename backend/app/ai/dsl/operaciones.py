"""
Catalogo declarativo del DSL de operaciones del asistente embebido.

Cada operacion envuelve algo que un motor determinista YA sabe hacer (ver
PLAN_ASISTENTE_IA.md, seccion 3.1): el modelo de IA solo elige CUAL de estas
operaciones usar y con que argumentos - nunca un valor que termine escrito
dentro de un archivo. Los argumentos de tipo "columna", "sufijo" y "campo" se
validan siempre contra lo que el contexto real tiene (interprete.py); el
modelo no puede nombrar algo que no exista.

Regla de crecimiento (seccion 3.1 del plan): no se agrega una operacion sin
un pedido real que la haya requerido.
"""
from __future__ import annotations

from dataclasses import dataclass

# Los dos unicos campos de una plantilla de receta que varian por registro
# (ver recetas_por_area.py: VarianteArea.linea_codigo / linea_descripcion).
CAMPOS_RECETA = ("#Codigo", "#Descripcion")

OPERACION_DESCONOCIDO = "desconocido"


@dataclass(frozen=True)
class ParametroOp:
    nombre: str
    tipo: str  # "columna" | "sufijos" | "campo" | "operador" | "texto"
    requerido: bool = True


@dataclass(frozen=True)
class DefinicionOperacion:
    nombre: str
    capa: str  # "gruesa" | "fina"
    descripcion: str
    parametros: tuple[ParametroOp, ...] = ()


OPERACIONES_GRUESAS: tuple[DefinicionOperacion, ...] = (
    DefinicionOperacion(
        nombre="generar_recetas_por_area",
        capa="gruesa",
        descripcion=(
            "Genera las recetas de cada fila del listado segun su area, "
            "igual que la pantalla 'Recetas por area'."
        ),
    ),
    DefinicionOperacion(
        nombre="generar_desde_plantilla",
        capa="gruesa",
        descripcion=(
            "Genera un archivo por fila a partir de una plantilla con campos "
            "{...} marcados, igual que la pantalla 'Generar desde plantilla'."
        ),
    ),
    DefinicionOperacion(
        nombre="tabular_mediciones",
        capa="gruesa",
        descripcion=(
            "Tabula un archivo de mediciones de ensayo a una planilla, igual "
            "que la pantalla 'Mediciones'."
        ),
    ),
)

# Operaciones finas: hoy solo el mundo "recetas por area" las soporta (son
# los pasos internos de generar_por_area(), vueltos componibles). Si otra
# pantalla necesita las suyas, se agregan cuando aparezca el pedido real.
OPERACIONES_FINAS: tuple[DefinicionOperacion, ...] = (
    DefinicionOperacion(
        nombre="filtrar_filas",
        capa="fina",
        descripcion="Recorta el listado a las filas que cumplen columna == valor.",
        parametros=(
            ParametroOp("columna", "columna"),
            ParametroOp("valor", "texto"),
        ),
    ),
    DefinicionOperacion(
        nombre="expandir_por_catalogo",
        capa="fina",
        descripcion="Expande cada fila a un archivo por sufijo del catalogo de su area.",
        parametros=(
            ParametroOp("solo_sufijos", "sufijos", requerido=False),
        ),
    ),
    DefinicionOperacion(
        nombre="reemplazar_campo",
        capa="fina",
        descripcion="Cambia que columna del listado alimenta un campo (#Codigo o #Descripcion) de la plantilla.",
        parametros=(
            ParametroOp("campo", "campo"),
            ParametroOp("columna", "columna"),
        ),
    ),
    DefinicionOperacion(
        nombre="nombrar_archivo",
        capa="fina",
        descripcion='Define el patron de nombre de archivo, ej. "{amortiguador}.{sufijo}.def.txt".',
        parametros=(
            ParametroOp("patron", "texto"),
        ),
    ),
    DefinicionOperacion(
        nombre="agrupar_salida_por",
        capa="fina",
        descripcion="Agrupa los archivos de salida en carpetas del .zip segun una columna.",
        parametros=(
            ParametroOp("columna", "columna"),
        ),
    ),
    DefinicionOperacion(
        nombre="quitar_comentarios",
        capa="fina",
        descripcion="Saca las lineas de nota '//' del resultado.",
    ),
)

TODAS: dict[str, DefinicionOperacion] = {
    op.nombre: op for op in OPERACIONES_GRUESAS + OPERACIONES_FINAS
}


def nombres_gruesas() -> list[str]:
    return [op.nombre for op in OPERACIONES_GRUESAS]


def nombres_finas() -> list[str]:
    return [op.nombre for op in OPERACIONES_FINAS]
