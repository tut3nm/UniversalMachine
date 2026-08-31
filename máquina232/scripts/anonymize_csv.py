"""Genera muestras anonimizadas de los CSV de recetas reales de planta.

Uso:
    py scripts/anonymize_csv.py <entrada.csv> <salida.csv>

Estrategia (ver PLAN_MEJORAS.md, Nivel 0.1):
- Filas 0 y 1 (declaración "List separator=...Decimal symbol=..." y el
  nombre de receta/categoría, p.ej. "Recipe_1 ", "C.VALVULAS "): son
  `filas_fijas` del perfil — contenido HARDCODEADO en profiles/*.json que
  el motor reescribe igual en cada guardado sin leerlo del archivo (ver
  DataStore._grid_columnas). Cambiar su texto acá rompería el round-trip
  byte-perfecto (el archivo quedaría con un nombre distinto al que el
  perfil va a regenerar al guardar), así que se preservan byte a byte.
- Filas cuyos valores de datos son exactamente la secuencia 1..N (fila
  índice): se preservan sin cambios — es metadata estructural, no dato de
  planta.
- El resto de las filas son datos: la primera celda es el NOMBRE DE CAMPO
  del formato (definido por el esquema de la máquina, no es información de
  la planta) y se preserva siempre. Cada celda de datos se clasifica en:
    * placeholder (vacío, "PATRON", "NC", "N/C") -> se preserva.
    * "código" (contiene alguna letra, o es una cadena de solo dígitos de
      6+ caracteres — típico de un código de artículo/pieza) -> se
      reemplaza carácter a carácter mediante una permutación FIJA por
      archivo (dígitos 1-9 entre sí, 'A'-'Z' entre sí, 'a'-'z' entre sí;
      el '0' se mantiene fijo). Al ser una sustitución consistente en todo
      el archivo, dos códigos reales iguales quedan iguales entre sí
      después de anonimizar, y — como el '0' nunca se mueve — dos códigos
      que sólo difieren en ceros a la izquierda (el criterio de
      duplicados 'ignorar_ceros' del perfil) siguen difiriendo sólo en
      ceros después de anonimizar. Es decir: se preserva la estructura de
      duplicados/relaciones entre códigos, no sólo el formato de cada uno
      por separado.
    * cualquier otro valor (mediciones numéricas/decimales) -> se baraja
      (permutación) entre las demás celdas "numéricas" de la MISMA fila.
      Esto reutiliza exactamente los mismos bytes que ya estaban en el
      archivo (ningún riesgo de romper el formato de decimales de ancho
      variable) y rompe la asociación código-real -> valor-real, que es lo
      que hace falta anonimizar.

No se anonimizan magnitudes agregadas (no hay estadísticas de resumen en
estos archivos), sólo se rompe la asociación fila-por-fila entre código de
producto y sus valores.
"""

from __future__ import annotations

import argparse
import random
import re
import string
import sys
from pathlib import Path

PLACEHOLDER_TOKENS = {"", "PATRON", "PATTERN", "NC", "N/C"}

# Patrón de slots vacíos del perfil 232 (profiles/maquina_232.json ->
# features.placeholder.patron = "^_DATA_\\d+$"). Estas celdas NO son
# códigos reales — son el relleno que `Profile.placeholder_template()`
# genera para posiciones sin producto asignado, y `DataStore.count_real()`
# los detecta por este patrón. Si se anonimizan como códigos comunes dejan
# de matchear el patrón y se cuentan como "reales" — hay que preservarlos.
DEFAULT_PLACEHOLDER_PATTERN = re.compile(r"^_DATA_\d+$")


def is_placeholder(cell: str, extra_pattern: re.Pattern | None = None) -> bool:
    c = cell.strip()
    if c.upper() in PLACEHOLDER_TOKENS:
        return True
    if DEFAULT_PLACEHOLDER_PATTERN.match(c):
        return True
    if extra_pattern is not None and extra_pattern.match(c):
        return True
    return False


def looks_like_code(cell: str) -> bool:
    c = cell.strip()
    if not c:
        return False
    if any(ch.isalpha() for ch in c):
        return True
    if c.isdigit() and len(c) >= 6:
        return True
    return False


def is_index_row(data: list[str]) -> bool:
    if not data:
        return False
    for i, cell in enumerate(data):
        if cell.strip() != str(i + 1):
            return False
    return True


class CharSubstitution:
    """Permutación fija dígito->dígito (0 fijo) y letra->letra (por case),
    consistente para todo un archivo. Al ser una biyección aplicada
    carácter a carácter, dos strings de entrada iguales producen la misma
    salida, y las relaciones de igualdad/diferencia por posición (p.ej. qué
    posiciones son '0') se preservan exactamente."""

    def __init__(self, rng: random.Random):
        digits = list("123456789")
        shuffled_digits = digits[:]
        rng.shuffle(shuffled_digits)
        self._digit_map = {"0": "0", **dict(zip(digits, shuffled_digits))}

        upper = list(string.ascii_uppercase)
        shuffled_upper = upper[:]
        rng.shuffle(shuffled_upper)
        self._upper_map = dict(zip(upper, shuffled_upper))
        self._lower_map = {k.lower(): v.lower() for k, v in self._upper_map.items()}

    def apply(self, orig: str) -> str:
        out = []
        for ch in orig:
            if ch in self._digit_map:
                out.append(self._digit_map[ch])
            elif ch in self._upper_map:
                out.append(self._upper_map[ch])
            elif ch in self._lower_map:
                out.append(self._lower_map[ch])
            else:
                out.append(ch)
        return "".join(out)


def anonymize_row(cells: list[str], subst: CharSubstitution,
                   rng: random.Random) -> list[str]:
    label, data = cells[0], cells[1:]

    if is_index_row(data):
        return cells

    code_positions = []
    other_positions = []
    for i, cell in enumerate(data):
        if is_placeholder(cell):
            continue
        if looks_like_code(cell):
            code_positions.append(i)
        else:
            other_positions.append(i)

    for i in code_positions:
        data[i] = subst.apply(data[i])

    if other_positions:
        values = [data[i] for i in other_positions]
        rng.shuffle(values)
        for pos, val in zip(other_positions, values):
            data[pos] = val

    return [label] + data


def process_file(in_path: Path, out_path: Path, seed: int = 1234,
                  filas_fijas: frozenset[int] = frozenset({0, 1})) -> None:
    raw = in_path.read_bytes()
    text = raw.decode("utf-8")
    eol = "\r\n" if "\r\n" in text else "\n"
    ends_with_eol = text.endswith(eol)
    lines = text.split(eol)
    if ends_with_eol:
        lines = lines[:-1]

    marker = "List separator="
    first_line = lines[0]
    idx = first_line.index(marker) + len(marker)
    delimiter = first_line[idx]

    rng = random.Random(seed)
    subst = CharSubstitution(rng)

    out_lines = []
    for i, line in enumerate(lines):
        if i in filas_fijas:
            out_lines.append(line)
            continue
        cells = line.split(delimiter)
        new_cells = anonymize_row(cells, subst, rng)
        assert len(new_cells) == len(cells), f"cambio de ancho de fila en línea {i}"
        out_lines.append(delimiter.join(new_cells))

    out_text = eol.join(out_lines)
    if ends_with_eol:
        out_text += eol
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_bytes(out_text.encode("utf-8"))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("entrada", type=Path)
    parser.add_argument("salida", type=Path)
    parser.add_argument("--seed", type=int, default=1234)
    parser.add_argument("--filas-fijas", type=str, default="0,1",
                         help="Índices de línea (0-based) a preservar byte a byte, "
                              "separados por coma. Deben coincidir con las "
                              "filas_fijas del perfil que lee este archivo.")
    args = parser.parse_args()
    filas_fijas = frozenset(int(x) for x in args.filas_fijas.split(",") if x.strip() != "")
    process_file(args.entrada, args.salida, args.seed, filas_fijas)
    print(f"OK: {args.entrada} -> {args.salida}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
