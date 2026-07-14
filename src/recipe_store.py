"""
recipe_store.py
================
Capa de datos del Configurador Máquina 232.

El archivo de recetas de la máquina 232 tiene un formato *transpuesto*:
cada COLUMNA es una pieza (registro) y cada FILA es un parámetro.

Estructura del CSV (7 filas, delimitado por ",", saltos de línea CRLF, sin BOM):

    fila 0:  List separator= , Decimal symbol=. , (relleno de comas)
    fila 1:  Recipe_1        , (relleno de comas)          <- ojo: espacio final
    fila 2:  LANGID_409      , <codigo1> , <codigo2> , ...  <- código de cada pieza
    fila 3:  3               , 1 , 2 , 3 , ...               <- posición (secuencial)
    fila 4:  Recetas_Datos Ingresados_Color            , <color1> , ...
    fila 5:  Recetas_Datos Ingresados_Gramos de Carga  , <gramos1> , ...
    fila 6:  Recetas_Datos Ingresados_Velocidad Inicio , <velocidad1> , ...

El ancho de cada fila es (1 + cantidad_de_registros). Las filas 0 y 1 se
rellenan con celdas vacías hasta ese ancho para mantener la grilla rectangular.

Este módulo carga ese formato a una lista simple de registros y lo vuelve a
escribir de forma idéntica al original.
"""

from __future__ import annotations

import csv
import io
import os
import re
import sys
from dataclasses import dataclass, field

# --- Etiquetas fijas (columna 0 de cada fila) --------------------------------
META_LABEL_1 = "List separator="
META_LABEL_2 = "Decimal symbol=."
RECIPE_LABEL = "Recipe_1 "          # incluye el espacio final del archivo original
LANGID_LABEL = "LANGID_409"
INDEX_LABEL = "3"
COLOR_LABEL = "Recetas_Datos Ingresados_Color"
GRAMS_LABEL = "Recetas_Datos Ingresados_Gramos de Carga"
SPEED_LABEL = "Recetas_Datos Ingresados_Velocidad Inicio"

# Fila EXTRA, propia de esta app (no existe en el formato de la máquina):
# marca qué registros ya fueron revisados y confirmados como "no es
# duplicado". Solo se guarda en el archivo de trabajo interno
# (datos232/actual.csv); nunca se incluye al exportar el CSV para el HMI
# (ver RecipeStore.to_rows(include_internal=False)).
REVIEW_LABEL = "Configurador232_RevisadoNoDuplicado"

# Un slot vacío (reservado) tiene un código con el patrón _DATA_<n>
PLACEHOLDER_RE = re.compile(r"^_DATA_\d+\s*$")

_ZERO_RE = re.compile(r"0")


def code_signature(code: str) -> str:
    """Firma para detectar posibles duplicados por relleno de ceros:
    conserva los caracteres del código que NO son el dígito '0',
    respetando su orden (p. ej. '00049810005962' y '004981005962'
    producen la misma firma)."""
    return _ZERO_RE.sub("", code or "")

# Rangos válidos observados en el archivo original (para validación de la UI)
COLOR_MIN, COLOR_MAX = 1, 3
GRAMS_MIN, GRAMS_MAX = 0, 9999
SPEED_MIN, SPEED_MAX = 0, 9999


@dataclass
class Recipe:
    """Una pieza / receta = una columna del CSV."""
    code: str
    color: int = 1
    grams: int = 0
    speed: int = 0
    # Metadato propio de la app (no viaja al CSV de la máquina): el usuario
    # revisó este código en "Duplicados" y confirmó que NO es un duplicado,
    # así que se excluye de futuras búsquedas de posibles duplicados.
    not_duplicate: bool = False

    @property
    def is_placeholder(self) -> bool:
        return bool(PLACEHOLDER_RE.match(self.code or ""))


def _to_int(value: str, default: int = 0) -> int:
    try:
        return int(str(value).strip())
    except (ValueError, TypeError):
        return default


class RecipeStore:
    """Colección de recetas con carga/guardado fiel al formato de la máquina."""

    def __init__(self, recipes: list[Recipe] | None = None):
        self.recipes: list[Recipe] = recipes or []

    # -- Carga -----------------------------------------------------------------
    @classmethod
    def load(cls, path: str) -> "RecipeStore":
        with open(path, "r", encoding="utf-8-sig", newline="") as f:
            rows = list(csv.reader(f))
        return cls.from_rows(rows)

    @classmethod
    def from_rows(cls, rows: list[list[str]]) -> "RecipeStore":
        if len(rows) < 7:
            raise ValueError(
                "El archivo no tiene el formato esperado de la máquina 232 "
                f"(se esperaban 7 filas, hay {len(rows)})."
            )

        def cell(row_idx: int, col_idx: int, default: str = "") -> str:
            row = rows[row_idx]
            return row[col_idx] if col_idx < len(row) else default

        # La cantidad de registros la marca la fila de códigos (fila 2),
        # descartando celdas vacías al final.
        codes_row = list(rows[2])
        while codes_row and codes_row[-1] == "":
            codes_row.pop()
        n = len(codes_row) - 1  # la columna 0 es la etiqueta

        # La fila de revisión de duplicados es opcional: solo la escribe esta
        # app en su archivo de trabajo interno. Si el archivo es el original
        # de fábrica (o uno exportado) no está, y se asume False para todos.
        review_row_idx = None
        if len(rows) > 7 and rows[7] and rows[7][0].strip() == REVIEW_LABEL:
            review_row_idx = 7

        recipes: list[Recipe] = []
        for c in range(1, n + 1):
            code = cell(2, c, f"_DATA_{c}").strip()
            if code == "":
                code = f"_DATA_{c}"
            not_dup = False
            if review_row_idx is not None:
                not_dup = cell(review_row_idx, c, "0").strip() == "1"
            recipes.append(
                Recipe(
                    code=code,
                    color=_to_int(cell(4, c), 1),
                    grams=_to_int(cell(5, c), 0),
                    speed=_to_int(cell(6, c), 0),
                    not_duplicate=not_dup,
                )
            )
        return cls(recipes)

    # -- Serialización ---------------------------------------------------------
    def to_rows(self, include_internal: bool = True) -> list[list[str]]:
        """Genera las filas del CSV. Con `include_internal=True` (por
        defecto) agrega la fila extra de "revisado, no es duplicado" que
        usa esta app para su archivo de trabajo. Con `include_internal=False`
        se genera el formato ORIGINAL de la máquina, sin esa fila — es el
        que hay que usar para cualquier archivo que se suba al HMI."""
        n = len(self.recipes)
        width = n + 1

        def padded(cells: list[str]) -> list[str]:
            return cells + [""] * (width - len(cells))

        row0 = padded([META_LABEL_1, META_LABEL_2])
        row1 = padded([RECIPE_LABEL])
        row2 = [LANGID_LABEL] + [r.code for r in self.recipes]
        row3 = [INDEX_LABEL] + [str(i) for i in range(1, n + 1)]
        row4 = [COLOR_LABEL] + [str(r.color) for r in self.recipes]
        row5 = [GRAMS_LABEL] + [str(r.grams) for r in self.recipes]
        row6 = [SPEED_LABEL] + [str(r.speed) for r in self.recipes]
        rows = [row0, row1, row2, row3, row4, row5, row6]
        if include_internal:
            row7 = [REVIEW_LABEL] + ["1" if r.not_duplicate else "0"
                                     for r in self.recipes]
            rows.append(row7)
        return rows

    def to_csv_text(self, include_internal: bool = True) -> str:
        buf = io.StringIO()
        writer = csv.writer(buf, lineterminator="\r\n")
        writer.writerows(self.to_rows(include_internal=include_internal))
        return buf.getvalue()

    def save(self, path: str, include_internal: bool = True) -> None:
        # newline="" evita que Python traduzca los saltos; el csv.writer ya
        # coloca CRLF explícito. Sin BOM, igual que el archivo original.
        with open(path, "w", encoding="utf-8", newline="") as f:
            f.write(self.to_csv_text(include_internal=include_internal))

    # -- Operaciones CRUD ------------------------------------------------------
    def add(self, recipe: Recipe) -> Recipe:
        """Agrega un registro al final."""
        self.recipes.append(recipe)
        return recipe

    def update(self, index: int, code: str, color: int, grams: int, speed: int) -> None:
        r = self.recipes[index]
        r.code, r.color, r.grams, r.speed = code, color, grams, speed

    def delete(self, index: int) -> Recipe:
        return self.recipes.pop(index)

    def find_code(self, code: str, exclude_index: int | None = None) -> int:
        """Devuelve el índice del primer registro con ese código, o -1."""
        target = (code or "").strip()
        for i, r in enumerate(self.recipes):
            if i == exclude_index:
                continue
            if r.code.strip() == target:
                return i
        return -1

    def next_placeholder_code(self) -> str:
        """Sugiere el siguiente código _DATA_<n> libre (para nuevos slots)."""
        used = set()
        for r in self.recipes:
            m = PLACEHOLDER_RE.match(r.code or "")
            if m:
                num = re.search(r"\d+", r.code)
                if num:
                    used.add(int(num.group()))
        n = len(self.recipes) + 1
        while n in used:
            n += 1
        return f"_DATA_{n}"

    def count_real(self) -> int:
        return sum(1 for r in self.recipes if not r.is_placeholder)

    def find_similar_groups(self) -> list[list[int]]:
        """Agrupa índices de registros reales cuyo código coincide al
        quitarle los dígitos '0' (ver code_signature). Devuelve solo los
        grupos con 2 o más registros, ordenados por firma. Los registros
        marcados como `not_duplicate` (revisados por el usuario) quedan
        afuera de la búsqueda."""
        groups: dict[str, list[int]] = {}
        for i, r in enumerate(self.recipes):
            if r.is_placeholder or r.not_duplicate:
                continue
            sig = code_signature(r.code)
            if not sig:
                continue
            groups.setdefault(sig, []).append(i)
        result = [idxs for idxs in groups.values() if len(idxs) > 1]
        result.sort(key=lambda idxs: self.recipes[idxs[0]].code.upper())
        return result


# --- Utilidades de rutas (soporta ejecución normal y empaquetada) ------------
def resource_path(rel: str) -> str:
    """Ruta a un recurso empaquetado (funciona con PyInstaller y en desarrollo)."""
    base = getattr(sys, "_MEIPASS", None)
    if base:
        return os.path.join(base, rel)
    # En desarrollo: el original vive en la raíz del proyecto (../ desde src/)
    here = os.path.dirname(os.path.abspath(__file__))
    candidates = [
        os.path.join(here, rel),
        os.path.join(here, "..", rel),
    ]
    for c in candidates:
        if os.path.exists(c):
            return os.path.abspath(c)
    return os.path.abspath(os.path.join(here, "..", rel))


def app_data_dir() -> str:
    """Carpeta escribible junto al ejecutable/proyecto donde viven los CSV."""
    if getattr(sys, "frozen", False):
        base = os.path.dirname(sys.executable)
    else:
        base = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    d = os.path.join(base, "datos232")
    os.makedirs(d, exist_ok=True)
    return d
