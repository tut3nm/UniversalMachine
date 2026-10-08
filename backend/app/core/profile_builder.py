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

from profile import ETIQUETA_ID_AUTO

# ---------------------------------------------------------------------------
#  Detección de formato de archivo
# ---------------------------------------------------------------------------

def detectar_codificacion(raw: bytes) -> tuple[str, bool]:
    """(codificación de Python, tiene_bom_utf8) de los bytes de un archivo.

    Orden: BOM UTF-16 / UTF-8, UTF-8 estricto, Windows-1252 (lo que exporta
    WinCC y Excel en español) y, como último recurso, latin-1 (nunca falla)."""
    if raw.startswith((b"\xff\xfe", b"\xfe\xff")):
        return "utf-16", False
    if raw.startswith(b"\xef\xbb\xbf"):
        return "utf-8", True
    for enc in ("utf-8", "cp1252"):
        try:
            raw.decode(enc)
            return enc, False
        except UnicodeDecodeError as e:
            pass
    return "latin-1", False


def sniff_csv(path: str) -> dict:
    """Detecta codificación, BOM, fin de línea, delimitador y símbolo decimal
    de un CSV."""
    with open(path, "rb") as f:
        completo = f.read()
    # La codificación se decide con el archivo entero: un solo carácter fuera
    # de UTF-8 pasado el primer bloque alcanza para que no sea UTF-8.
    encoding, bom = detectar_codificacion(completo)
    raw = completo[:65536]
    text = raw.decode("utf-8-sig" if encoding == "utf-8" else encoding, errors="replace")
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
            "simbolo_decimal": simbolo_decimal, "encoding": encoding}


def read_grid(path: str, delimitador: str, encoding: str | None = None) -> list[list[str]]:
    """Lee el archivo completo como grilla de celdas. Sin `encoding`, lo
    detecta de los bytes (ver detectar_codificacion)."""
    if encoding is None:
        with open(path, "rb") as f:
            encoding, _ = detectar_codificacion(f.read())
    with open(path, encoding="utf-8-sig" if encoding == "utf-8" else encoding,
              newline="") as f:
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


def suggest_clave_row(grid: list[list[str]], primera_col: int,
                      aproximada: bool = True) -> int | None:
    """Primera fila con valores todos distintos entre sí: heurística simple
    para sugerir cuál es el código/clave de cada pieza. Se prefiere una fila
    de TEXTO (más probable que sea un código real y no una medición), pero si
    ninguna fila de texto califica se acepta la primera fila puramente
    numérica con valores únicos como respaldo (p. ej. un código de pieza que
    resulta ser numérico, como RNROAMORTIGUADOR=4717012798): es mejor
    sugerir ese candidato, aunque sea numérico, que no sugerir nada y dejar
    que la UI caiga por defecto a la fila 0 (que casi nunca es la clave).

    Si NINGUNA fila tiene valores 100% únicos (exports reales a veces
    repiten un código en variantes distintas del mismo modelo), se ofrece
    como último recurso la fila con más valores casi-únicos (mayor
    proporción de distintos/total, con más valores en total como
    desempate) en vez de no sugerir nada (salvo `aproximada=False`: el wizard
    prefiere proponer un ID automático antes que una clave con repetidos)."""
    candidato_numerico: int | None = None
    mejor_aprox: tuple[float, int, int] | None = None  # (proporción, r, total)
    for r, row in enumerate(grid):
        valores = [c.strip() for c in row[primera_col:] if c.strip() != ""]
        if len(valores) < 2:
            continue

        distintos = len(set(valores))
        if distintos != len(valores):
            proporcion = distintos / len(valores)
            candidato = (proporcion, r, len(valores))
            if mejor_aprox is None or candidato[0] > mejor_aprox[0]:
                mejor_aprox = candidato
            continue  # tiene repetidos: no puede ser clave única

        try:
            nums = [float(v) for v in valores]
        except ValueError:
            return r  # candidato de texto, 100% único: se prefiere siempre
        else:
            # una secuencia consecutiva (1, 2, 3, ...) es un índice
            # autogenerado, no un código real: no calificar como candidato.
            if all(b - a == 1 for a, b in zip(nums, nums[1:])):
                continue
            if candidato_numerico is None:
                candidato_numerico = r

    if candidato_numerico is not None:
        return candidato_numerico
    if not aproximada:
        return None  # el wizard prefiere ID automático a una clave con repetidos
    return mejor_aprox[1] if mejor_aprox is not None else None


# ---------------------------------------------------------------------------
#  Detección de tipo + formato para un campo, a partir de una muestra
# ---------------------------------------------------------------------------

def campo_id_automatico() -> dict:
    """Campo clave sintético: no existe en el archivo de la máquina."""
    return {
        "nombre_interno": "id", "rol": "clave", "tipo": "entero",
        "titulo_ui": "ID", "etiqueta": ETIQUETA_ID_AUTO,
        "visible": True, "sintetica": True,
    }


def _fila_ancla(grid: list[list[str]], primera_col: int) -> int:
    """Sin campo clave, primera fila que ya es dato por registro: lo que
    queda ANTES son encabezados del export (título, separadores, filas
    vacías) y se conservan como filas fijas. Es la primera fila con valores
    que varían entre registros (o la secuencia 1..N, si viene antes)."""
    for r in range(len(grid)):
        if classify_row(grid, r, primera_col) != "fija":
            return r
    return 0


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
                            clave_row: int | None, campos_elegidos: list[dict],
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

    `clave_row=None`: el archivo no tiene una fila que identifique a cada
    registro. El perfil lleva un campo clave sintético (ID automático, ver
    campo_id_automatico) y las filas anteriores a la primera fila con datos
    variables quedan como filas fijas.
    """
    row_kinds = row_kinds or {}
    id_auto = clave_row is None
    ancla = _fila_ancla(grid, primera_col) if id_auto else (clave_row or 0)
    elegidas_por_fila = {c["fila"]: c for c in campos_elegidos}
    max_fila = len(grid) - 1

    perfil: dict = {
        "id": machine_id,
        "nombre": nombre,
        "descripcion": descripcion,
        "archivo_inicial": archivo_inicial,
        "archivo": {
            "extension": info.get("extension", "csv"),
            "delimitador": info["delimitador"],
            "encoding": info.get("encoding", "utf-8"),
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
    if id_auto:
        campos.append(campo_id_automatico())
        used_names.add("id")

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
            if kind == "fija" and (r >= ancla if id_auto else r > ancla):
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
                         primera_fila_datos: int, clave_col: int | None,
                         campos_elegidos: list[dict],
                         features: dict | None = None) -> dict:
    """Arma el perfil JSON (orientacion='filas': CSV normal, un registro por
    fila). Igual que build_profile_columnas pero en el otro eje: toda columna
    no elegida como campo visible se agrega como campo oculto. Con
    `clave_col=None` la clave es un ID automático (ver campo_id_automatico)."""
    header = grid[header_row] if header_row < len(grid) else []
    elegidas_por_col = {c["columna"]: c for c in campos_elegidos}
    used_names: set[str] = {c["nombre_interno"] for c in campos_elegidos}

    campos = []
    if clave_col is None:
        campos.append(campo_id_automatico())
        used_names.add("id")
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
            "extension": info.get("extension", "csv"), "delimitador": info["delimitador"],
            "encoding": info.get("encoding", "utf-8"), "bom": info["bom"],
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
                        "encoding": info.get("encoding", "utf-8"), "bom": info["bom"],
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
                        "encoding": info.get("encoding", "utf-8"), "bom": info["bom"],
                        "fin_de_linea": info["fin_de_linea"], "orientacion": "columnas"},
            "estructura": {"columna_etiquetas": 0, "primera_columna_datos": 1},
            "campos": campos,
        }

    else:
        raise ValueError(f"Orientación desconocida: {orientacion!r}")
