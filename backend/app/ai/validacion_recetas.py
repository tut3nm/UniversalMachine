"""
Reglas DETERMINISTAS de validacion de consistencia para el mundo "recetas
por area" (PLAN_ASISTENTE_IA.md, seccion 5). No usan IA: los dos defectos
reales que motivaron este modulo se encuentran con reglas simples de texto,
sin hacer falta ningun modelo.

- RecetasHD/001789002323.17.def.txt tiene '#Descripcion;47700019342' (11
  digitos), mientras que las variantes .15 y .19 del MISMO sellado
  (001789002323) tienen '471700019342' (12) - falta un digito en una de las
  tres. Lo cazan auditar_archivos()/auditar_carpeta() (regla
  'descripcion_inconsistente_entre_variantes').
- RecetasGPS2/Obsoletos/004981008611.20.def.txt tiene '#Codigo;001789010000',
  que no coincide con su propio nombre de archivo (esa carpeta queda fuera
  del alcance normal de auditar_repositorio() porque son sufijos obsoletos
  que ya no se generan, pero la regla 'codigo_no_coincide_con_archivo' la
  detectaria igual si se la apunta ahi).

Modulo puro (sin FastAPI ni I/O mas alla de leer los .txt), mismo criterio
que recetas_por_area.py: mas facil de testear con fixtures chicas.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from app.ai.plantillas_masivas import _decode

_NOMBRE_RE = re.compile(r"^([^.]+)\.(.+)\.def\.txt$", re.IGNORECASE)
_LINEA_MAQUINA_RE = re.compile(r"^#Maquina;([^;]*);([^;]*);([^;]*);([^;]*)")


@dataclass(frozen=True)
class Hallazgo:
    regla: str
    archivo: str
    mensaje: str


def _sellado_y_sufijo(nombre_archivo: str) -> tuple[str, str] | None:
    m = _NOMBRE_RE.match(nombre_archivo)
    return (m.group(1), m.group(2)) if m else None


def _valor_de_linea(lineas: list[str], prefijo: str) -> str | None:
    for linea in lineas:
        if linea.startswith(prefijo):
            return linea[len(prefijo):]
    return None


def _tep_de(lineas: list[str]) -> str | None:
    for linea in lineas:
        m = _LINEA_MAQUINA_RE.match(linea)
        if m:
            return m.group(4)
    return None


# --- auditoria de plantillas de referencia (docs/Recetas/<AREA>/) ----------


def auditar_archivos(archivos: dict[str, str]) -> list[Hallazgo]:
    """`archivos`: {nombre_archivo: contenido}, todos de UNA misma area (mismo
    alcance que recetas_por_area.cargar_catalogo). No toca disco: la funcion
    que sí lee la carpeta es auditar_carpeta(), mas abajo."""
    hallazgos: list[Hallazgo] = []
    por_sellado: dict[str, list[str]] = {}

    for nombre, contenido in archivos.items():
        info = _sellado_y_sufijo(nombre)
        if info is None:
            continue
        sellado, sufijo = info
        lineas = contenido.splitlines()

        codigo = _valor_de_linea(lineas, "#Codigo;")
        if codigo is not None and codigo != sellado:
            hallazgos.append(Hallazgo(
                "codigo_no_coincide_con_archivo", nombre,
                f"#Codigo;{codigo} no coincide con el nombre del archivo (sellado {sellado}).",
            ))

        tep = _tep_de(lineas)
        if tep is not None and tep != "" and not tep.startswith(sufijo):
            hallazgos.append(Hallazgo(
                "tep_no_coincide_con_sufijo", nombre,
                f"El TEP ({tep}) no arranca con el sufijo de operacion ({sufijo}).",
            ))

        por_sellado.setdefault(sellado, []).append(nombre)

    for sellado, nombres in por_sellado.items():
        if len(nombres) < 2:
            continue
        descripciones = {
            nombre: _valor_de_linea(archivos[nombre].splitlines(), "#Descripcion;")
            for nombre in nombres
        }
        valores_distintos = {v for v in descripciones.values() if v is not None}
        if len(valores_distintos) > 1:
            detalle = ", ".join(f"{n}: #Descripcion;{v}" for n, v in sorted(descripciones.items()))
            for nombre in nombres:
                hallazgos.append(Hallazgo(
                    "descripcion_inconsistente_entre_variantes", nombre,
                    f"Las variantes del sellado '{sellado}' no tienen el mismo #Descripcion ({detalle}).",
                ))

    return hallazgos


def auditar_carpeta(carpeta: Path) -> list[Hallazgo]:
    """Audita solo los .txt del nivel superior de la carpeta (mismo alcance
    que cargar_catalogo: Nuevo/Nuevos/Obsoletos quedan afuera)."""
    archivos = {p.name: _decode(p.read_bytes()) for p in sorted(carpeta.glob("*.txt"))}
    return auditar_archivos(archivos)


# --- validacion del listado que sube el usuario -----------------------------


def validar_listado(
    filas: list[dict], col_sellado: str, col_amortiguador: str, col_area: str
) -> list[Hallazgo]:
    """Errores de carga tipicos: campos vacios, no-numericos donde siempre
    hay numero, y sellados repetidos entre filas (no bloquea la generacion -
    generar_por_area ya les agrega un sufijo '_2' - pero suele ser un
    indicio de que se pegaron dos veces la misma fila)."""
    hallazgos: list[Hallazgo] = []
    filas_por_sellado: dict[str, list[int]] = {}

    for i, fila in enumerate(filas, start=1):
        origen = f"fila {i}"
        sellado = fila.get(col_sellado, "").strip()
        amortiguador = fila.get(col_amortiguador, "").strip()
        area = fila.get(col_area, "").strip()

        if not sellado:
            hallazgos.append(Hallazgo("campo_vacio", origen, "Falta el sellado."))
        elif not sellado.isdigit():
            hallazgos.append(Hallazgo("campo_no_numerico", origen, f"El sellado '{sellado}' no es numerico."))

        if not amortiguador:
            hallazgos.append(Hallazgo("campo_vacio", origen, "Falta el amortiguador."))
        elif not amortiguador.isdigit():
            hallazgos.append(Hallazgo("campo_no_numerico", origen, f"El amortiguador '{amortiguador}' no es numerico."))

        if not area:
            hallazgos.append(Hallazgo("campo_vacio", origen, "Falta el area."))

        if sellado:
            filas_por_sellado.setdefault(sellado, []).append(i)

    for sellado, indices in filas_por_sellado.items():
        if len(indices) > 1:
            hallazgos.append(Hallazgo(
                "codigo_repetido", f"filas {indices}",
                f"El sellado '{sellado}' aparece en mas de una fila ({', '.join(map(str, indices))}).",
            ))

    return hallazgos
