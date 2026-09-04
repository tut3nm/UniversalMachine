"""
profile_builder.py
===================
Motor de detección y armado de perfiles, usado por el wizard de alta de
máquina ("Agregar máquina"): a partir de un CSV de muestra,

  1. detecta delimitador, codificación, fin de línea, BOM y símbolo decimal;
  2. sugiere, para cada fila/columna, si es un candidato a "campo" (valores
     variados por registro), a "fila fija" (metadata, constante/vacía en
     todos los registros) o a "fila índice" (secuencia 1..N);
  3. sugiere, para una muestra de valores de un campo, su tipo (texto /
     entero / entero_ceros / decimal) y el 'formato' correspondiente (ancho
     de ceros, separador y cantidad de decimales);
  4. arma el perfil JSON final a partir de las elecciones del usuario en el
     wizard, dejando TODO lo no elegido explícitamente como campo oculto
     (visible=False) para no perder nunca una celda del archivo original.

Nada de esto reemplaza la validación real: el wizard debe cargar el perfil
resultante con DataStore y comparar el re-guardado byte a byte contra el
archivo original antes de confirmar el alta (ver App._wizard_validar en
app.py / WizardMachineDialog).
"""

from __future__ import annotations

import csv
import re

# ---------------------------------------------------------------------------
#  Detección de formato de archivo
# ---------------------------------------------------------------------------

def sniff_csv(path: str) -> dict:
    """Detecta BOM, fin de línea, delimitador y símbolo decimal de un CSV."""
    with open(path, "rb") as f:
        raw = f.read(65536)
    bom = raw.startswith(b"\xef\xbb\xbf")
    text = raw.decode("utf-8-sig", errors="replace")
    if "\r\n" in text:
        fin = "CRLF"
    elif "\r" in text and "\n" not in text:
        fin = "CR"
    else:
        fin = "LF"
    try:
        dialect = csv.Sniffer().sniff(text, delimiters=[",", ";", "\t", "|"])
        delimitador = dialect.delimiter
    except csv.Error:
        delimitador = ","

    simbolo_decimal = None
    m = re.search(r"Decimal symbol\s*=\s*(.)", text, re.IGNORECASE)
    if m:
        simbolo_decimal = m.group(1)

    return {"bom": bom, "fin_de_linea": fin, "delimitador": delimitador,
            "simbolo_decimal": simbolo_decimal}


def read_grid(path: str, delimitador: str) -> list[list[str]]:
    with open(path, encoding="utf-8-sig", newline="") as f:
        return list(csv.reader(f, delimiter=delimitador))


# ---------------------------------------------------------------------------
#  Clasificación de filas/columnas (para orientacion == "columnas")
# ---------------------------------------------------------------------------

def classify_row(grid: list[list[str]], row_idx: int, primera_col: int) -> str:
    """Sugiere qué es una fila (para el paso de vista previa del wizard):
      "indice" -> secuencia 1..N (o N..1): candidata a fila_indice
                  (se renumera sola al agregar/borrar registros).
      "fija"   -> mismo valor (o vacío) en todos los registros: candidata a
                  fila fija / metadata (encabezado del bloque, símbolos, etc).
      "dato"   -> valores variados: candidata a campo (visible u oculto).
    Es solo una sugerencia inicial; el usuario decide en el wizard."""
    if row_idx >= len(grid):
        return "dato"
    row = grid[row_idx]
    valores = [c for c in row[primera_col:] if c != ""]
    if not valores:
        return "fija"

    # ¿Secuencia 1..N (o con offset constante)?
    try:
        nums = [int(v) for v in valores]
        if len(nums) > 2 and all(b - a == 1 for a, b in zip(nums, nums[1:])):
            return "indice"
    except ValueError:
        pass

    distintos = set(valores)
    if len(distintos) <= 1:
        return "fija"
    return "dato"


def suggest_clave_row(grid: list[list[str]], primera_col: int) -> int | None:
    """Primera fila con valores no numéricos y todos distintos entre sí:
    heurística simple para sugerir cuál es el código/clave de cada pieza."""
    for r, row in enumerate(grid):
        valores = [c.strip() for c in row[primera_col:] if c.strip() != ""]
        if len(valores) < 2:
            continue
        if len(set(valores)) != len(valores):
            continue  # tiene repetidos: no puede ser clave única
        try:
            [float(v) for v in valores]
            continue  # es puramente numérica: probablemente no es el código
        except ValueError:
            return r
    return None


# ---------------------------------------------------------------------------
#  Detección de tipo + formato para un campo, a partir de una muestra
# ---------------------------------------------------------------------------

_INT_RE = re.compile(r"^[+-]?\d+$")


def _decimal_re(sep: str) -> re.Pattern:
    return re.compile(rf"^[+-]?\d+{re.escape(sep)}\d+$")


def suggest_tipo(valores: list[str], simbolo_decimal_hint: str | None = None) -> dict:
    """Analiza una muestra de valores crudos de un campo y sugiere
    {"tipo": ..., "formato": {...}}. Si los valores no son consistentes con
    ningún tipo numérico (p. ej. mezclan texto centinela como "N/C" con
    números), sugiere "texto" — la opción segura: el motor preserva cada
    celda cruda tal cual mientras no se edite, así que "texto" nunca pierde
    datos, solo implica que ese campo no se valida/edita como número."""
    vals = [v.strip() for v in valores if v is not None and str(v).strip() != ""]
    if not vals:
        return {"tipo": "texto", "formato": {}}

    if all(_INT_RE.match(v) for v in vals):
        anchos = [len(v.lstrip("+-")) for v in vals]
        con_ceros = any(v.lstrip("+-").startswith("0") and len(v.lstrip("+-")) > 1
                         for v in vals)
        if con_ceros:
            return {"tipo": "entero_ceros", "formato": {"ancho": max(anchos)}}
        return {"tipo": "entero", "formato": {}}

    candidatos_sep = [simbolo_decimal_hint] if simbolo_decimal_hint else []
    candidatos_sep += [s for s in (",", ".") if s not in candidatos_sep]
    for sep in candidatos_sep:
        rx = _decimal_re(sep)
        if all(rx.match(v) for v in vals):
            decimales = max(len(v.split(sep)[1]) for v in vals)
            return {"tipo": "decimal",
                    "formato": {"separador_decimal": sep, "decimales": decimales}}

    return {"tipo": "texto", "formato": {}}


def _slug(text: str, fallback_idx: int, used: set[str]) -> str:
    """Nombre interno seguro para un campo (identificador único)."""
    s = re.sub(r"[^a-zA-Z0-9]+", "_", (text or "").strip().lower()).strip("_")
    if not s:
        s = f"campo_{fallback_idx}"
    base, n = s, 2
    while s in used:
        s = f"{base}_{n}"
        n += 1
    used.add(s)
    return s


# ---------------------------------------------------------------------------
#  Armado final del perfil a partir de las elecciones del usuario
# ---------------------------------------------------------------------------

def build_profile_columnas(machine_id: str, nombre: str, descripcion: str,
                            archivo_inicial: str, info: dict,
                            grid: list[list[str]], primera_col: int,
                            clave_row: int, campos_elegidos: list[dict],
                            row_kinds: dict[int, str] | None = None,
                            features: dict | None = None) -> dict:
    """Arma el perfil JSON (orientacion='columnas') a partir de lo que el
    usuario definió en el wizard.

    `campos_elegidos`: lista de dicts (en cualquier orden), uno por cada fila
        que el usuario quiere como campo VISIBLE:
        {"fila": int, "nombre_interno": str, "titulo_ui": str, "tipo": str,
         "formato": dict, "min": float|None, "max": float|None,
         "default": object|None}
        La fila == clave_row debe estar incluida (rol clave).
    `row_kinds`: clasificación sugerida/confirmada por fila (de classify_row),
        usada SOLO para las filas que el usuario no eligió como campo, para
        decidir si van como "fila fija" (constante) o "fila índice"
        (secuencia auto-renumerada) en vez de campo oculto genérico.
    Toda fila del archivo que no sea clave_row, no esté en campos_elegidos y
    no se detecte como fija/índice, se agrega como campo OCULTO
    (visible=False): viaja con cada registro y se preserva byte a byte, pero
    nunca se muestra ni se edita en la UI.
    """
    row_kinds = row_kinds or {}
    elegidas_por_fila = {c["fila"]: c for c in campos_elegidos}
    max_fila = len(grid) - 1

    perfil: dict = {
        "id": machine_id,
        "nombre": nombre,
        "descripcion": descripcion,
        "archivo_inicial": archivo_inicial,
        "archivo": {
            "extension": "csv",
            "delimitador": info["delimitador"],
            "encoding": "utf-8",
            "bom": info["bom"],
            "fin_de_linea": info["fin_de_linea"],
            "orientacion": "columnas",
        },
        "estructura": {
            "columna_etiquetas": 0,
            "primera_columna_datos": primera_col,
            "filas_fijas": [],
            "fila_indice": None,
        },
        "campos": [],
        "features": features or {},
    }

    used_names: set[str] = set()
    for c in campos_elegidos:
        used_names.add(c["nombre_interno"])

    filas_fijas = []
    fila_indice = None
    campos = []

    for r in range(max_fila + 1):
        # `etiqueta` se guarda SIN recortar: es la celda de columna 0, que
        # datastore._grid_columnas() vuelve a escribir tal cual al
        # reconstruir el archivo (round-trip byte a byte). Si se guardara
        # recortada, un espacio final/inicial legítimo en el export original
        # (p. ej. "Modelos Amortiguador ") se perdería en cada reconstrucción.
        # `etiqueta_ui` (recortada) es solo para título/slug sugeridos.
        etiqueta = grid[r][0] if r < len(grid) and grid[r] else ""
        etiqueta_ui = etiqueta.strip()

        if r == clave_row:
            c = elegidas_por_fila.get(r, {})
            campos.append({
                "nombre_interno": c.get("nombre_interno") or _slug(etiqueta_ui, r, used_names),
                "rol": "clave", "fila": r, "etiqueta": etiqueta,
                "tipo": "texto", "titulo_ui": c.get("titulo_ui") or etiqueta_ui or "Código",
                "visible": True,
            })
            continue

        if r in elegidas_por_fila:
            c = elegidas_por_fila[r]
            campo = {
                "nombre_interno": c["nombre_interno"], "rol": "parametro",
                "fila": r, "etiqueta": etiqueta,
                "tipo": c.get("tipo", "texto"), "titulo_ui": c.get("titulo_ui") or etiqueta_ui,
                "visible": True,
            }
            if c.get("formato"):
                campo["formato"] = c["formato"]
            if c.get("min") is not None:
                campo["min"] = c["min"]
            if c.get("max") is not None:
                campo["max"] = c["max"]
            if c.get("default") is not None:
                campo["default"] = c["default"]
            campos.append(campo)
            continue

        if r in row_kinds:
            kind = row_kinds[r]  # elección explícita del usuario (wizard): se respeta tal cual
        else:
            kind = classify_row(grid, r, primera_col)
            if kind == "fija" and r > clave_row:
                # Una fila DESPUÉS de la clave es, por definición, un dato
                # por registro (aunque hoy sea constante en toda la muestra:
                # un parámetro de proceso puede coincidir para todas las
                # piezas actuales y aun así variar el día de mañana). La
                # SUGERENCIA automática nunca propone "fija" ahí, para no
                # arriesgar el ancho de la fila al agregar/borrar — pero si
                # el usuario la elige a propósito (row_kinds), se respeta.
                kind = "dato"
        if kind == "fija":
            celdas = list(grid[r]) if r < len(grid) else []
            # recortar celdas vacías al final: se regeneran con 'rellenar'
            while celdas and celdas[-1] == "":
                celdas.pop()
            filas_fijas.append({"fila": r, "celdas": celdas, "rellenar": True})
        elif kind == "indice" and fila_indice is None:
            fila_indice = {"fila": r, "etiqueta": etiqueta, "base": 1}
        else:
            # Campo oculto: preserva cada celda cruda por registro, viaja con
            # alta/baja, nunca se muestra ni se edita.
            campos.append({
                "nombre_interno": _slug(etiqueta_ui or f"oculto_{r}", r, used_names),
                "rol": "parametro", "fila": r, "etiqueta": etiqueta,
                "tipo": "texto", "titulo_ui": etiqueta_ui or f"Fila {r + 1}",
                "visible": False,
            })

    perfil["estructura"]["filas_fijas"] = filas_fijas
    perfil["estructura"]["fila_indice"] = fila_indice
    perfil["campos"] = campos
    return perfil


def build_profile_filas(machine_id: str, nombre: str, descripcion: str,
                         archivo_inicial: str, info: dict,
                         grid: list[list[str]], header_row: int,
                         primera_fila_datos: int, clave_col: int,
                         campos_elegidos: list[dict],
                         features: dict | None = None) -> dict:
    """Arma el perfil JSON (orientacion='filas': CSV normal, un registro por
    fila). Igual que build_profile_columnas pero en el otro eje: toda columna
    no elegida como campo visible se agrega como campo oculto."""
    header = grid[header_row] if header_row < len(grid) else []
    elegidas_por_col = {c["columna"]: c for c in campos_elegidos}
    used_names: set[str] = {c["nombre_interno"] for c in campos_elegidos}

    campos = []
    for i, h in enumerate(header):
        etiqueta = (h or "").strip()
        if i == clave_col:
            c = elegidas_por_col.get(i, {})
            campos.append({
                "nombre_interno": c.get("nombre_interno") or _slug(etiqueta, i, used_names),
                "rol": "clave", "columna": i, "etiqueta": etiqueta,
                "tipo": "texto", "titulo_ui": c.get("titulo_ui") or etiqueta or f"Columna {i + 1}",
                "visible": True,
            })
        elif i in elegidas_por_col:
            c = elegidas_por_col[i]
            campo = {
                "nombre_interno": c["nombre_interno"], "rol": "parametro",
                "columna": i, "etiqueta": etiqueta,
                "tipo": c.get("tipo", "texto"), "titulo_ui": c.get("titulo_ui") or etiqueta,
                "visible": True,
            }
            if c.get("formato"):
                campo["formato"] = c["formato"]
            if c.get("min") is not None:
                campo["min"] = c["min"]
            if c.get("max") is not None:
                campo["max"] = c["max"]
            if c.get("default") is not None:
                campo["default"] = c["default"]
            campos.append(campo)
        else:
            campos.append({
                "nombre_interno": _slug(etiqueta or f"oculto_{i}", i, used_names),
                "rol": "parametro", "columna": i, "etiqueta": etiqueta,
                "tipo": "texto", "titulo_ui": etiqueta or f"Columna {i + 1}",
                "visible": False,
            })

    return {
        "id": machine_id, "nombre": nombre, "descripcion": descripcion,
        "archivo_inicial": archivo_inicial,
        "archivo": {
            "extension": "csv", "delimitador": info["delimitador"],
            "encoding": "utf-8", "bom": info["bom"],
            "fin_de_linea": info["fin_de_linea"], "orientacion": "filas",
        },
        "estructura": {"fila_encabezado": header_row,
                        "primera_fila_datos": primera_fila_datos},
        "campos": campos,
        "features": features or {},
    }


# ---------------------------------------------------------------------------
#  Compatibilidad: alta rápida de un solo paso (un campo por fila/columna,
#  todo visible). La usa el modo "avanzado" del wizard y los tests viejos.
# ---------------------------------------------------------------------------

def build_scaffold(machine_id: str, nombre: str, descripcion: str,
                    archivo_inicial: str, csv_path: str,
                    orientacion: str, clave_row: int = 0) -> dict:
    """Arma un perfil JSON borrador de un solo campo por fila/columna
    (equivalente al alta 'rápida' anterior). `orientacion`: "filas" o
    "columnas"; `clave_row` indica la fila del código si es "columnas"."""
    info = sniff_csv(csv_path)
    grid = read_grid(csv_path, info["delimitador"])
    if not grid or not any(grid):
        raise ValueError("El archivo CSV está vacío o no se pudo leer.")

    if orientacion == "filas":
        header = grid[0]
        sample = grid[1:11]
        used_names: set[str] = set()
        campos = []
        for i, h in enumerate(header):
            titulo = (h or "").strip() or f"Columna {i + 1}"
            es_clave = i == 0
            valores = [r[i] for r in sample if i < len(r)]
            sug = {"tipo": "texto", "formato": {}} if es_clave else \
                suggest_tipo(valores, info.get("simbolo_decimal"))
            campo = {
                "nombre_interno": _slug(titulo, i, used_names),
                "rol": "clave" if es_clave else "parametro",
                "columna": i, "etiqueta": (h or "").strip(),
                "tipo": sug["tipo"], "titulo_ui": titulo,
            }
            if sug.get("formato"):
                campo["formato"] = sug["formato"]
            campos.append(campo)
        return {
            "id": machine_id, "nombre": nombre, "descripcion": descripcion,
            "archivo_inicial": archivo_inicial,
            "archivo": {"extension": "csv", "delimitador": info["delimitador"],
                        "encoding": "utf-8", "bom": info["bom"],
                        "fin_de_linea": info["fin_de_linea"], "orientacion": "filas"},
            "estructura": {"fila_encabezado": 0, "primera_fila_datos": 1},
            "campos": campos,
        }

    elif orientacion == "columnas":
        if not (0 <= clave_row < len(grid)):
            raise ValueError(
                f"La fila del código ({clave_row}) está fuera de rango: "
                f"el archivo tiene {len(grid)} filas.")
        used_names: set[str] = set()
        campos = []
        for r, row in enumerate(grid):
            # sin recortar: se reescribe tal cual al reconstruir el archivo
            # (ver comentario equivalente en build_profile_columnas).
            etiqueta = row[0] if row else ""
            etiqueta_ui = etiqueta.strip()
            es_clave = r == clave_row
            titulo = etiqueta_ui or ("Código" if es_clave else f"Fila {r + 1}")
            if es_clave:
                sug = {"tipo": "texto", "formato": {}}
            else:
                sug = suggest_tipo(row[1:11], info.get("simbolo_decimal"))
            campo = {
                "nombre_interno": _slug(titulo, r, used_names),
                "rol": "clave" if es_clave else "parametro",
                "fila": r, "etiqueta": etiqueta,
                "tipo": sug["tipo"], "titulo_ui": titulo,
            }
            if sug.get("formato"):
                campo["formato"] = sug["formato"]
            campos.append(campo)
        return {
            "id": machine_id, "nombre": nombre, "descripcion": descripcion,
            "archivo_inicial": archivo_inicial,
            "archivo": {"extension": "csv", "delimitador": info["delimitador"],
                        "encoding": "utf-8", "bom": info["bom"],
                        "fin_de_linea": info["fin_de_linea"], "orientacion": "columnas"},
            "estructura": {"columna_etiquetas": 0, "primera_columna_datos": 1},
            "campos": campos,
        }

    else:
        raise ValueError(f"Orientación desconocida: {orientacion!r}")
