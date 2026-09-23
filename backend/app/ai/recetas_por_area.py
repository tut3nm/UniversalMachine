"""
Generador de recetas por area (segunda parte de PLAN_GENERADOR_RECETAS.md).

Diferencia con plantillas_masivas.py: ahi el campo variable se marca a mano
con {...} + comentario "//" en una unica plantilla generica, provista por el
usuario en cada corrida. Aca no hace falta marcar nada: los archivos de
ejemplo reales de docs/Recetas/Recetas<AREA>/ (uno por cada "sufijo" de
operacion que existe hoy para esa area, ej. "004981008610.17.def.txt")
identifican por convencion de nombre de campo cuales son las dos lineas que
varian por registro:
    #Codigo;...        -> sellado (tambien da nombre al archivo)
    #Descripcion;...   -> amortiguador
El resto de cada plantilla (#Operacion, #Maquina...) es fijo por sufijo
dentro de esa area: comparando varios ejemplos con el mismo sufijo y
distinto codigo, esos valores no cambian.

Modulo puro (sin FastAPI ni I/O de sesion), mismo criterio que
plantillas_masivas.py.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

from app.ai.plantillas_masivas import _decode, _detectar_eol, _normalizar, leer_listado

_SUFIJO_RE = re.compile(r"^[^.]+\.(.+)\.def\.txt$", re.IGNORECASE)
_LINEA_CODIGO_PREFIJO = "#Codigo;"
_LINEA_DESCRIPCION_PREFIJO = "#Descripcion;"


# ---------------------------------------------------------------------------
# Catalogo de plantillas por area (una por sufijo de operacion)
# ---------------------------------------------------------------------------


@dataclass
class VarianteArea:
    sufijo: str                    # "15", "13.5", etc., tal cual aparece en el nombre de archivo
    lineas: list[str]              # contenido original de ESA plantilla, linea por linea
    eol: str                       # fin de linea original (CRLF/LF), para reconstruir igual
    linea_codigo: int              # indice de la linea "#Codigo;..."
    linea_descripcion: int         # indice de la linea "#Descripcion;..."


@dataclass
class CatalogoArea:
    area: str                      # "HD", "GPS1", "GPS2"
    variantes: list[VarianteArea]


def _sufijo_desde_nombre(nombre_archivo: str) -> str:
    m = _SUFIJO_RE.match(nombre_archivo)
    if not m:
        raise ValueError(
            f"'{nombre_archivo}' no respeta el nombre esperado '<codigo>.<sufijo>.def.txt'."
        )
    return m.group(1)


def _parsear_variante(nombre_archivo: str, texto: str) -> VarianteArea:
    eol = _detectar_eol(texto)
    lineas = texto.splitlines()
    idx_codigo = next((i for i, l in enumerate(lineas) if l.startswith(_LINEA_CODIGO_PREFIJO)), None)
    idx_descripcion = next(
        (i for i, l in enumerate(lineas) if l.startswith(_LINEA_DESCRIPCION_PREFIJO)), None
    )
    if idx_codigo is None or idx_descripcion is None:
        raise ValueError(
            f"'{nombre_archivo}' no tiene una linea '{_LINEA_CODIGO_PREFIJO}' y "
            f"'{_LINEA_DESCRIPCION_PREFIJO}' (son las dos que el motor reemplaza por registro)."
        )
    return VarianteArea(
        sufijo=_sufijo_desde_nombre(nombre_archivo),
        lineas=lineas,
        eol=eol,
        linea_codigo=idx_codigo,
        linea_descripcion=idx_descripcion,
    )


def cargar_catalogo(carpeta: Path, area: str) -> CatalogoArea:
    """Lee las plantillas de referencia de UNA area: solo los .txt del nivel
    superior de la carpeta (las subcarpetas Nuevo/Nuevos/Obsoletos no se leen:
    Obsoletos son sufijos que ya no se generan, y Nuevo/Nuevos son ejemplos
    adicionales que no aportan sufijos nuevos, ver PLAN_GENERADOR_RECETAS.md)."""
    variantes = [
        _parsear_variante(p.name, _decode(p.read_bytes()))
        for p in sorted(carpeta.glob("*.txt"))
    ]
    if not variantes:
        raise ValueError(f"No hay plantillas de referencia para el area '{area}' en {carpeta}.")
    return CatalogoArea(area=area, variantes=variantes)


# ---------------------------------------------------------------------------
# Generacion
# ---------------------------------------------------------------------------


@dataclass
class RegistroGeneradoArea:
    nombre_archivo: str
    contenido: str
    area: str
    sufijo: str
    fila_origen: int               # numero de fila del listado (1-based, sin contar encabezado)


@dataclass
class ResultadoGeneracionArea:
    archivos: list[RegistroGeneradoArea] = field(default_factory=list)
    filas_sin_area: list[int] = field(default_factory=list)   # filas cuya "area" no matchea ningun catalogo
    areas_usadas: dict[str, int] = field(default_factory=dict)  # area -> cantidad de registros


def _buscar_columna_unica(encabezados_norm: dict[str, str], nombre: str) -> str:
    candidatas = [h for h, n in encabezados_norm.items() if n == nombre]
    if len(candidatas) != 1:
        raise ValueError(
            f"El listado debe tener exactamente una columna '{nombre}' "
            f"(encontradas: {len(candidatas)})."
        )
    return candidatas[0]


def generar_por_area(
    catalogos: dict[str, CatalogoArea], encabezados: list[str], filas: list[dict]
) -> ResultadoGeneracionArea:
    encabezados_norm = {h: _normalizar(h) for h in encabezados}
    col_sellado = _buscar_columna_unica(encabezados_norm, "sellado")
    col_amortiguador = _buscar_columna_unica(encabezados_norm, "amortiguador")
    col_area = _buscar_columna_unica(encabezados_norm, "area")

    resultado = ResultadoGeneracionArea()
    nombres_usados: dict[str, int] = {}

    for i, fila in enumerate(filas, start=1):
        area_valor = fila.get(col_area, "").strip()
        catalogo = catalogos.get(_normalizar(area_valor))
        if catalogo is None:
            resultado.filas_sin_area.append(i)
            continue

        sellado = fila.get(col_sellado, "").strip()
        if not sellado:
            raise ValueError(f"La fila {i} del listado no tiene valor de sellado.")
        amortiguador = fila.get(col_amortiguador, "").strip()

        for variante in catalogo.variantes:
            lineas = list(variante.lineas)
            lineas[variante.linea_codigo] = f"{_LINEA_CODIGO_PREFIJO}{sellado}"
            lineas[variante.linea_descripcion] = f"{_LINEA_DESCRIPCION_PREFIJO}{amortiguador}"

            base = f"{sellado}.{variante.sufijo}"
            contador = nombres_usados.get(base, 0) + 1
            nombres_usados[base] = contador
            sufijo_dup = "" if contador == 1 else f"_{contador}"
            nombre_archivo = f"{base}{sufijo_dup}.def.txt"

            resultado.archivos.append(
                RegistroGeneradoArea(
                    nombre_archivo=nombre_archivo,
                    contenido=variante.eol.join(lineas),
                    area=catalogo.area,
                    sufijo=variante.sufijo,
                    fila_origen=i,
                )
            )

        resultado.areas_usadas[catalogo.area] = resultado.areas_usadas.get(catalogo.area, 0) + 1

    return resultado
