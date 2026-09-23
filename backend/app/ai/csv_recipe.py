"""
Lectura y reescritura de archivos CSV tipo "receta" (matriz parametro x producto),
como los que usan varias maquinas para su puesta a punto por material.

Formato tipico:
    List separator=,Decimal symbol=.
    Recipe_1
    LANGID_409,<codigo prod 1>,<codigo prod 2>,...
    3,1,2,3,...
    <Nombre parametro 1>,<valor prod1>,<valor prod2>,...
    <Nombre parametro 2>,<valor prod1>,<valor prod2>,...
    ...

Diferencia de diseño respecto de structure.py (el motor de logs de ensayo):
esto es una matriz CSV limpia y regular (todas las filas con la misma
cantidad de columnas), no texto libre con asteriscos. Por eso se lee/escribe
con el modulo csv estandar en vez de tokenizar caracter por caracter: es mas
simple, mas predecible, y mas seguro para un archivo que despues se va a
cargar en una maquina de produccion.

SEGURIDAD: la reconstruccion nunca "regenera desde cero" el archivo. Toma el
original como base, cambia UNICAMENTE las celdas que el usuario efectivamente
edito en Excel, y se autoverifica releyendo el resultado antes de darlo por
bueno. Ademas siempre devuelve un listado con cada cambio detectado, para que
se pueda revisar antes de cargarlo en el equipo.
"""
from __future__ import annotations

import csv
import io
import os
from dataclasses import dataclass, field
from typing import Optional


# ---------------------------------------------------------------------------
# Deteccion
# ---------------------------------------------------------------------------


def sniff(path: str) -> tuple[bool, str]:
    """Indica si un archivo tiene forma de 'matriz de receta' (filas parametro
    x columnas producto, todas las filas con igual cantidad de campos)."""
    if not path.lower().endswith((".csv", ".txt")):
        return False, "La extension no es .csv"
    try:
        with open(path, "rb") as f:
            raw = f.read(200_000)
    except OSError as exc:
        return False, f"No se pudo leer el archivo: {exc}"

    text = _decode(raw)
    lines = text.splitlines()
    if len(lines) < 3:
        return False, "Muy pocas lineas para ser una matriz de receta."

    delim = "," if lines[0].count(",") >= lines[0].count(";") else ";"
    counts = [len(next(csv.reader([l], delimiter=delim), [])) for l in lines[:20] if l.strip()]
    if not counts:
        return False, "No se pudo determinar la cantidad de columnas."
    common = max(set(counts), key=counts.count)
    ratio = counts.count(common) / len(counts)
    if common < 3 or ratio < 0.7:
        return False, "Las filas no tienen una cantidad de columnas consistente."
    return True, f"Parece una matriz CSV de {common} columnas."


def _decode(raw: bytes) -> str:
    for enc in ("utf-8-sig", "cp1252", "latin-1"):
        try:
            return raw.decode(enc)
        except UnicodeDecodeError:
            continue
    return raw.decode("latin-1", errors="replace")


def _detect_line_ending(raw: bytes) -> str:
    if b"\r\n" in raw:
        return "\r\n"
    if b"\n" in raw:
        return "\n"
    return os.linesep


# ---------------------------------------------------------------------------
# Estructura
# ---------------------------------------------------------------------------


@dataclass
class ParamRow:
    name: str
    values: list          # texto tal cual, una entrada por producto
    row_index: int         # indice de fila dentro de 'rows' (0-based, archivo completo)


@dataclass
class RecipeFile:
    header_rows: list         # filas de metadatos, ANTES de la fila de codigos de producto, tal cual (list[list[str]])
    product_row_index: int    # indice de la fila que tiene los codigos de producto
    product_codes: list       # codigos de producto (sin la primera columna)
    extra_rows: list          # filas entre la fila de codigos y la primera fila de parametros (ej. la fila "3,1,2,3,...")
    params: list               # list[ParamRow]
    delimiter: str
    line_ending: str
    encoding_used: str
    has_bom: bool
    total_columns: int
    n_data_columns: int        # columnas de producto (total_columns - 1)


def read_recipe(path: str) -> RecipeFile:
    with open(path, "rb") as f:
        raw = f.read()
    line_ending = _detect_line_ending(raw)
    has_bom = raw.startswith(b"\xef\xbb\xbf")
    text = _decode(raw)
    encoding_used = "utf-8-sig" if has_bom else "utf-8"

    lines = text.splitlines()
    delim = "," if (lines[0].count(",") if lines else 0) >= (lines[0].count(";") if lines else 1) else ";"

    reader_rows = [next(csv.reader([l], delimiter=delim), []) for l in lines]
    col_counts = [len(r) for r in reader_rows if r]
    common = max(set(col_counts), key=col_counts.count) if col_counts else 0

    # la fila de codigos de producto: la primera fila "larga" (>= common) cuya
    # primera celda NO es puramente numerica con muchos decimales tipicos de
    # una fila de datos, y que tiene muchas celdas no vacias distintas entre si
    product_row_index = None
    for i, row in enumerate(reader_rows):
        if len(row) >= common and len(row) > 2:
            non_empty = [c for c in row[1:] if c.strip()]
            if len(non_empty) >= common - 2:
                product_row_index = i
                break
    if product_row_index is None:
        raise ValueError("No se pudo identificar la fila de codigos de producto.")

    header_rows = reader_rows[:product_row_index]
    product_codes = reader_rows[product_row_index][1:]

    # filas siguientes que no tienen forma de "nombre de parametro + numeros"
    # se tratan como filas extra de metadatos (ej. una fila de indices 1..N)
    params: list[ParamRow] = []
    extra_rows: list[tuple[int, list]] = []
    i = product_row_index + 1
    while i < len(reader_rows):
        row = reader_rows[i]
        if not row:
            i += 1
            continue
        name = row[0].strip()
        values = row[1:]
        if len(values) < len(product_codes):
            values = values + [""] * (len(product_codes) - len(values))
        elif len(values) > len(product_codes):
            values = values[:len(product_codes)]
        if name and not _looks_like_index_row(name, values):
            params.append(ParamRow(name=name, values=values, row_index=i))
        else:
            extra_rows.append((i, row))
        i += 1

    return RecipeFile(
        header_rows=header_rows,
        product_row_index=product_row_index,
        product_codes=product_codes,
        extra_rows=extra_rows,
        params=params,
        delimiter=delim,
        line_ending=line_ending,
        encoding_used=encoding_used,
        has_bom=has_bom,
        total_columns=common,
        n_data_columns=len(product_codes),
    )


def _looks_like_index_row(name: str, values: list) -> bool:
    """Filas tipo '3,1,2,3,4,5,...' (indices correlativos): no son un
    parametro editable, son metadatos internos del formato."""
    try:
        nums = [float(v) for v in values if v.strip() != ""]
    except ValueError:
        return False
    if len(nums) < 5:
        return False
    seq = list(range(1, len(nums) + 1))
    matches = sum(1 for a, b in zip(nums, seq) if a == b)
    return matches / len(nums) > 0.9


# ---------------------------------------------------------------------------
# Escritura del CSV final (a partir del original + ediciones)
# ---------------------------------------------------------------------------


@dataclass
class CellChange:
    parametro: str
    producto: str
    valor_anterior: str
    valor_nuevo: str


@dataclass
class ReverseResult:
    ok: bool
    output_path: str = ""
    changes: list = field(default_factory=list)
    warnings: list = field(default_factory=list)
    error: str = ""


def _render_row(name: str, values: list, delimiter: str) -> str:
    out = io.StringIO()
    w = csv.writer(out, delimiter=delimiter, lineterminator="")
    w.writerow([name] + list(values))
    return out.getvalue()


def rebuild_csv(
    original_path: str,
    recipe: RecipeFile,
    edited_values: dict,   # (param_name, product_code) -> nuevo valor (texto)
    output_path: str,
) -> ReverseResult:
    """Reconstruye el CSV a partir del ORIGINAL, cambiando unicamente las
    filas de parametro que tengan al menos un valor editado.

    Todo lo demas (lineas de encabezado, fila de codigos de producto, filas
    de indices, saltos de linea, cualquier fila que no sea un parametro
    reconocido) queda BYTE A BYTE igual al archivo original: se copian las
    lineas crudas tal cual, sin volver a serializarlas.
    """
    changes: list[CellChange] = []
    warnings: list[str] = []

    with open(original_path, "rb") as f:
        raw = f.read()
    text = _decode(raw)
    raw_lines = text.splitlines()

    out_lines: list[str] = list(raw_lines)

    # 1. validar que los codigos de producto de las ediciones sean EXACTAMENTE
    # los del original: si alguno no coincide (fila borrada, agregada, o
    # codigo mal tipeado en Excel), esas ediciones se ignoran silenciosamente
    # mas abajo, asi que hay que avisarlo en vez de dejarlo pasar.
    edited_codes = {code for (_name, code) in edited_values.keys()}
    original_codes = set(recipe.product_codes)
    codigos_desconocidos = sorted(edited_codes - original_codes)
    if codigos_desconocidos:
        muestra = ", ".join(codigos_desconocidos[:10])
        mas = f" (+{len(codigos_desconocidos)-10} mas)" if len(codigos_desconocidos) > 10 else ""
        warnings.append(
            f"El Excel tiene {len(codigos_desconocidos)} código(s) de producto que no "
            f"están en el archivo original: {muestra}{mas}. Los cambios en esas filas "
            "NO se aplicaron. Revisar si se escribió mal el código o se agregó una fila."
        )

    for p in recipe.params:
        new_values = list(p.values)
        row_changed = False
        # tipo predominante de la fila original (numerico vs texto), para
        # avisar si una edicion lo rompe (ej. escribir texto donde siempre
        # hubo numeros, tipico error de tipeo)
        originally_numeric = _mostly_numeric(p.values)
        for j, product_code in enumerate(recipe.product_codes):
            key = (p.name, product_code)
            if key not in edited_values:
                continue
            new_val = edited_values[key]
            old_val = p.values[j]
            if _normalize(new_val) != _normalize(old_val):
                if new_val.strip() == "" and old_val.strip() != "":
                    warnings.append(
                        f"'{p.name}' / '{product_code}': se dejó el valor vacío (antes era "
                        f"'{old_val}'). Confirmar que la máquina interpreta bien un valor en "
                        "blanco para este parámetro antes de usarlo."
                    )
                elif originally_numeric and new_val.strip() != "" and not _is_numeric(new_val):
                    warnings.append(
                        f"'{p.name}' / '{product_code}': el valor nuevo ('{new_val}') no es "
                        "numérico, pero el resto de esa fila sí lo es. Verificar que no sea "
                        "un error de tipeo antes de usar este archivo."
                    )
                changes.append(CellChange(p.name, product_code, old_val, new_val))
                new_values[j] = new_val
                row_changed = True
        if row_changed:
            out_lines[p.row_index] = _render_row(p.name, new_values, recipe.delimiter)

    output_text = recipe.line_ending.join(out_lines)
    # preservar si el archivo original terminaba con salto de linea final
    if text.endswith(("\r\n", "\n")) and not output_text.endswith(("\r\n", "\n")):
        output_text += recipe.line_ending

    try:
        with open(output_path, "w", encoding=recipe.encoding_used, newline="") as f:
            f.write(output_text)
    except OSError as exc:
        return ReverseResult(ok=False, error=f"No se pudo guardar el archivo: {exc}")

    # autoverificacion: releer el archivo recien escrito y confirmar que cada
    # cambio pedido quedo reflejado, y que nada mas se movio de lugar
    verify = read_recipe(output_path)
    verify_map = {p.name: p for p in verify.params}
    for ch in changes:
        vp = verify_map.get(ch.parametro)
        if vp is None:
            warnings.append(f"No se pudo reverificar el parametro '{ch.parametro}'.")
            continue
        try:
            idx = recipe.product_codes.index(ch.producto)
        except ValueError:
            continue
        if _normalize(vp.values[idx]) != _normalize(ch.valor_nuevo):
            warnings.append(
                f"ALERTA: '{ch.parametro}' / '{ch.producto}' no coincide tras "
                f"releer el archivo generado (se guardo '{vp.values[idx]}', se "
                f"esperaba '{ch.valor_nuevo}'). Revisar antes de usar este archivo."
            )
    if verify.total_columns != recipe.total_columns or len(verify.params) != len(recipe.params):
        warnings.append(
            "ALERTA: la estructura del archivo generado (cantidad de columnas o "
            "de parametros) no coincide con la del original. No usar sin revisar."
        )

    return ReverseResult(ok=not any(w.startswith("ALERTA") for w in warnings),
                         output_path=output_path, changes=changes, warnings=warnings)


def _normalize(v) -> str:
    return str(v).strip()


def _is_numeric(v) -> bool:
    try:
        float(str(v).strip().replace(",", "."))
        return True
    except ValueError:
        return False


def _mostly_numeric(values: list, threshold: float = 0.9) -> bool:
    non_empty = [v for v in values if str(v).strip() != ""]
    if not non_empty:
        return False
    return sum(1 for v in non_empty if _is_numeric(v)) / len(non_empty) >= threshold


# ---------------------------------------------------------------------------
# Excel: producto por fila, parametro por columna (mas comodo para buscar
# y editar una receta puntual que desplazarse por cientos de columnas)
# ---------------------------------------------------------------------------

PRODUCT_COL = "Código de producto"
SHEET_RECETAS = "Recetas"


def write_excel_recipe(recipe: RecipeFile, output_path: str, source_path: str) -> None:
    from datetime import datetime
    from openpyxl import Workbook
    from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
    from openpyxl.utils import get_column_letter

    TITLE_FONT = Font(name="Calibri", size=15, bold=True, color="1F4E78")
    SUBTITLE_FONT = Font(name="Calibri", size=10, italic=True, color="595959")
    NOTE_FONT = Font(name="Calibri", size=10, color="7F6000")
    WARN_FILL = PatternFill("solid", fgColor="FFF2CC")
    HEADER_FONT = Font(name="Calibri", size=10, bold=True, color="FFFFFF")
    HEADER_FILL = PatternFill("solid", fgColor="1F4E78")
    PRODUCT_FONT = Font(name="Calibri", size=10, bold=True)
    PRODUCT_FILL = PatternFill("solid", fgColor="D9E1F2")
    THIN = Side(style="thin", color="D9D9D9")
    BORDER = Border(left=THIN, right=THIN, top=THIN, bottom=THIN)

    wb = Workbook()

    # ---- hoja de instrucciones -------------------------------------------
    ws0 = wb.active
    ws0.title = "Instrucciones"
    ws0.sheet_view.showGridLines = False
    r = 1
    ws0.cell(row=r, column=1, value="Edición de recetas de máquina").font = TITLE_FONT
    r += 1
    ws0.cell(row=r, column=1, value=f"Archivo origen: {os.path.basename(source_path)}").font = SUBTITLE_FONT
    r += 1
    ws0.cell(row=r, column=1,
            value=f"Generado: {datetime.now().strftime('%d/%m/%Y %H:%M:%S')}").font = SUBTITLE_FONT
    r += 2
    instrucciones = [
        "CÓMO USAR ESTE ARCHIVO",
        "1. En la hoja 'Recetas', cada fila es un producto y cada columna un parámetro.",
        "2. Editá únicamente los valores que quieras cambiar. No agregues ni borres filas o columnas.",
        "3. No cambies el texto de 'Código de producto' de ninguna fila: es lo que identifica",
        "   a qué producto corresponde cada fila al reconstruir el archivo.",
        "4. Guardá el Excel (Ctrl+S) sin cambiar el nombre del archivo ni la hoja.",
        "5. Volvé al programa y usá 'Aplicar cambios al archivo original' con este Excel",
        "   y el archivo .csv ORIGINAL (el mismo que se uso para generar este Excel).",
        "",
        "IMPORTANTE",
        "- El programa NO reescribe el archivo entero: compara este Excel contra el original",
        "  y cambia únicamente las celdas que hayan cambiado. Todo lo demás queda intacto.",
        "- Antes de cargar el archivo generado en la máquina, revisar el listado de",
        "  cambios que el programa muestra al terminar.",
        "- Este Excel no reemplaza el control que ya tenga la empresa para autorizar",
        "  cambios de puesta a punto en producción.",
    ]
    for line in instrucciones:
        cell = ws0.cell(row=r, column=1, value=line)
        if line in ("CÓMO USAR ESTE ARCHIVO", "IMPORTANTE"):
            cell.font = Font(name="Calibri", size=11, bold=True, color="1F4E78")
        else:
            cell.font = Font(name="Calibri", size=10)
        r += 1
    ws0.column_dimensions["A"].width = 100

    # ---- hoja de recetas (transpuesta) ------------------------------------
    ws = wb.create_sheet(SHEET_RECETAS)
    headers = [PRODUCT_COL] + [p.name for p in recipe.params]
    for c, h in enumerate(headers, start=1):
        cell = ws.cell(row=1, column=c, value=h)
        cell.font = HEADER_FONT
        cell.fill = HEADER_FILL
        cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
        cell.border = BORDER
    ws.row_dimensions[1].height = 40
    ws.freeze_panes = "B2"
    ws.auto_filter.ref = f"A1:{get_column_letter(len(headers))}1"

    for i, code in enumerate(recipe.product_codes):
        row = i + 2
        c0 = ws.cell(row=row, column=1, value=code)
        c0.font = PRODUCT_FONT
        c0.fill = PRODUCT_FILL
        c0.border = BORDER
        for j, p in enumerate(recipe.params):
            v = p.values[i]
            cell = ws.cell(row=row, column=2 + j, value=_as_excel_value(v))
            cell.border = BORDER

    widths = {"A": 22}
    for j in range(len(recipe.params)):
        widths[get_column_letter(2 + j)] = 16
    for col, w in widths.items():
        ws.column_dimensions[col].width = w

    wb.active = 1
    wb.save(output_path)


def _as_excel_value(v: str):
    v = v.strip() if isinstance(v, str) else v
    if v == "":
        return None
    try:
        f = float(v)
        return int(f) if f.is_integer() else f
    except (TypeError, ValueError):
        return v


def read_edited_excel(xlsx_path: str) -> dict:
    """Lee la hoja 'Recetas' del Excel editado.

    Devuelve {(nombre_parametro, codigo_producto): valor_como_texto}
    """
    from openpyxl import load_workbook

    wb = load_workbook(xlsx_path, read_only=True, data_only=True)
    if SHEET_RECETAS not in wb.sheetnames:
        raise ValueError(f"El Excel no tiene una hoja llamada '{SHEET_RECETAS}'.")
    ws = wb[SHEET_RECETAS]

    rows = list(ws.iter_rows(values_only=True))
    if not rows:
        raise ValueError("La hoja 'Recetas' está vacía.")
    header = rows[0]
    if not header or header[0] != PRODUCT_COL:
        raise ValueError(
            f"La primera columna de la hoja 'Recetas' debe llamarse '{PRODUCT_COL}'. "
            "No se detectó: puede que se haya modificado el encabezado."
        )
    param_names = list(header[1:])

    out: dict[tuple, str] = {}
    for row in rows[1:]:
        if not row or row[0] in (None, ""):
            continue
        code = str(row[0]).strip()
        for j, pname in enumerate(param_names):
            if pname is None:
                continue
            val = row[1 + j] if 1 + j < len(row) else None
            out[(pname, code)] = _to_text(val)
    wb.close()
    return out


def _to_text(v) -> str:
    if v is None:
        return ""
    if isinstance(v, float) and v.is_integer():
        return str(int(v))
    return str(v)
