"""
excel_import.py
================
Lectura de archivos Excel (.xlsx/.xlsm) de formato variable para la función
"Importar cambios" del Configurador Máquina 232.

Como cada Excel puede traer las columnas en distinto orden o con distintos
encabezados, este módulo separa la lectura en dos pasos:

  1. `open_workbook` / `sheet_names` / `read_headers`: exploran el archivo
     para que la interfaz le pida al usuario qué columna corresponde a
     Código, Color, Gramos de Carga y Velocidad Inicio.
  2. `read_rows`: una vez que el usuario confirmó el mapeo, recorre los
     datos usando esas columnas.
"""

from __future__ import annotations

from dataclasses import dataclass

import openpyxl

# Palabras clave para sugerir automáticamente el mapeo de columnas según el
# texto del encabezado (todo en minúsculas, sin acentos).
_HEADER_HINTS = {
    "code": ("codigo", "código", "code", "pieza", "parte", "part", "sku"),
    "color": ("color",),
    "grams": ("gramo", "carga", "aceite", "peso", "oil"),
    "speed": ("veloc", "speed", "rpm"),
}


def _strip_accents(text: str) -> str:
    replacements = str.maketrans("áéíóúÁÉÍÓÚñÑ", "aeiouAEIOUnN")
    return text.translate(replacements)


@dataclass
class ExcelRow:
    """Una fila de datos ya emparejada según el mapeo de columnas."""
    raw_code: object
    raw_color: object
    raw_grams: object
    raw_speed: object


def open_workbook(path: str):
    """Abre el libro en modo solo-lectura, con fórmulas resueltas a valor."""
    return openpyxl.load_workbook(path, data_only=True, read_only=True)


def sheet_names(workbook) -> list[str]:
    return list(workbook.sheetnames)


def read_headers(workbook, sheet: str) -> list[str]:
    """Devuelve los encabezados (fila 1) de la hoja indicada."""
    ws = workbook[sheet]
    row_iter = ws.iter_rows(min_row=1, max_row=1, values_only=True)
    first_row = next(row_iter, ())
    headers = []
    for i, h in enumerate(first_row):
        text = str(h).strip() if h is not None else ""
        headers.append(text if text else f"(columna {i + 1})")
    return headers


def guess_mapping(headers: list[str]) -> dict[str, int | None]:
    """Sugiere a qué índice de columna corresponde cada campo, buscando
    palabras clave en los encabezados. Devuelve None si no encuentra nada
    razonable, para que el usuario deba confirmarlo."""
    guess: dict[str, int | None] = {"code": None, "color": None,
                                    "grams": None, "speed": None}
    for i, h in enumerate(headers):
        norm = _strip_accents(h.lower())
        for field, hints in _HEADER_HINTS.items():
            if guess[field] is None and any(hint in norm for hint in hints):
                guess[field] = i
    return guess


def read_rows(workbook, sheet: str, col_code: int, col_color: int,
              col_grams: int, col_speed: int) -> list[ExcelRow]:
    """Lee todas las filas de datos (a partir de la fila 2) usando los
    índices de columna ya confirmados por el usuario."""
    ws = workbook[sheet]
    rows: list[ExcelRow] = []
    max_col = max(col_code, col_color, col_grams, col_speed)
    for raw in ws.iter_rows(min_row=2, values_only=True):
        if raw is None or len(raw) <= max_col:
            continue
        if all(cell is None for cell in raw):
            continue
        rows.append(ExcelRow(
            raw_code=raw[col_code],
            raw_color=raw[col_color],
            raw_grams=raw[col_grams],
            raw_speed=raw[col_speed],
        ))
    return rows


def normalize_code(raw: object) -> str:
    """Convierte el valor crudo de una celda de código a texto comparable.
    Excel suele guardar códigos numéricos como número (p. ej. 4981005962.0),
    perdiendo los ceros a la izquierda; acá se normaliza a texto entero."""
    if raw is None:
        return ""
    if isinstance(raw, float) and raw.is_integer():
        raw = int(raw)
    return str(raw).strip()


def normalize_int(raw: object) -> int | None:
    """Convierte el valor crudo de una celda numérica (Color, Gramos,
    Velocidad) a int. Devuelve None si la celda está vacía o no es
    interpretable, para no pisar el valor actual con basura."""
    if raw is None:
        return None
    if isinstance(raw, (int, float)):
        return int(round(raw))
    text = str(raw).strip().replace(",", ".")
    if not text:
        return None
    try:
        return int(round(float(text)))
    except ValueError:
        return None
