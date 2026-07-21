"""
datastore.py
============
Motor genérico de datos, guiado por un Profile (perfil.py). Reemplaza al
antiguo recipe_store.py, que tenía el formato de la 232 cableado.

Cada registro es un `dict[str, valor]` con claves = nombre_interno de cada
campo del perfil. El motor no sabe qué es "color" o "gramos": lee el perfil
para saber dónde está cada dato y cómo reconstruir el archivo byte por byte.

Los metadatos propios de la app (marca "no es duplicado", etc.) NO viven acá:
van en un archivo sidecar aparte (metadata.py), keyeados por el valor de la
clave. Así el CSV que se sube al HMI mantiene siempre el formato original.
"""

from __future__ import annotations

import csv
import io

from profile import Campo, Profile


def _to_number(value: str, campo: Campo):
    """Parsea el string crudo de una celda al valor tipado del campo (para
    ordenar, validar min/max y mostrar en la UI). Si el texto no matchea el
    tipo esperado (celda "N/C", "PATRON", vacía, etc.) cae al default: el
    string CRUDO original igual se preserva aparte y es el que se vuelve a
    escribir al guardar mientras la celda no se edite (ver DataStore._raw)."""
    txt = str(value).strip()
    if txt == "":
        return campo.default if campo.default is not None else 0
    if campo.tipo == "decimal":
        sep = campo.formato.get("separador_decimal", ",") if campo.formato else ","
        miles = campo.formato.get("separador_miles", "") if campo.formato else ""
        limpio = txt
        if miles:
            limpio = limpio.replace(miles, "")
        limpio = limpio.replace(sep, ".") if sep != "." else limpio
        # Compatibilidad con perfiles viejos sin 'formato': aceptar coma o punto.
        if sep != "," and "," in limpio:
            limpio = limpio.replace(",", ".")
        try:
            return float(limpio)
        except ValueError:
            return campo.default if campo.default is not None else 0.0
    if campo.tipo in ("entero", "entero_ceros"):
        miles = campo.formato.get("separador_miles", "") if campo.formato else ""
        limpio = txt.replace(miles, "") if miles else txt
        try:
            return int(round(float(limpio)))
        except ValueError:
            return campo.default if campo.default is not None else 0
    return campo.default if campo.default is not None else 0


def _format_value(value, campo: Campo) -> str:
    """Formatea un valor tipado (editado por el usuario) al string que se
    escribe en el CSV, según el tipo y 'formato' del campo. Solo se usa para
    celdas que el usuario efectivamente editó o para registros nuevos: las
    celdas sin tocar se preservan crudas (ver DataStore._raw)."""
    if campo.tipo == "entero":
        try:
            n = int(value)
        except (ValueError, TypeError):
            return str(value)
        miles = campo.formato.get("separador_miles", "") if campo.formato else ""
        txt = str(n)
        if miles:
            txt = f"{n:,}".replace(",", miles)
        return txt
    if campo.tipo == "entero_ceros":
        try:
            n = int(value)
        except (ValueError, TypeError):
            return str(value)
        ancho = int(campo.formato.get("ancho", 1)) if campo.formato else 1
        signo = "-" if n < 0 else ""
        return signo + str(abs(n)).zfill(ancho)
    if campo.tipo == "decimal":
        try:
            f = float(value)
        except (ValueError, TypeError):
            return str(value)
        if campo.formato and "decimales" in campo.formato:
            decimales = int(campo.formato["decimales"])
            sep = campo.formato.get("separador_decimal", ".")
            miles = campo.formato.get("separador_miles", "")
            entero_part, _, dec_part = f"{f:.{decimales}f}".partition(".")
            if miles:
                neg = entero_part.startswith("-")
                digitos = entero_part[1:] if neg else entero_part
                grupos = []
                while len(digitos) > 3:
                    grupos.insert(0, digitos[-3:])
                    digitos = digitos[:-3]
                grupos.insert(0, digitos)
                entero_part = ("-" if neg else "") + miles.join(grupos)
            return entero_part + (sep + dec_part if dec_part else "")
        # Sin 'formato' explícito (perfiles viejos, ej. 232): comportamiento
        # legado, sin ceros de más.
        return str(int(f)) if f.is_integer() else str(f)
    return "" if value is None else str(value)


class DataStore:
    """Colección de registros de un archivo, con carga/guardado fiel al
    formato definido por el perfil.

    Preservación byte-perfecta ("raw-preserve"): además del valor tipado de
    cada campo (rec[nombre_interno], usado por la UI/validaciones tal como
    siempre), cada registro guarda aparte (en self._raw, alineado por índice
    con self.records) el string EXACTO que tenía esa celda en el archivo
    original. Al guardar, una celda no editada se reescribe con ese string
    crudo tal cual (conserva ceros a la izquierda, cantidad de decimales,
    centinelas como "N/C" o "PATRON", etc.); solo se reformatea desde el
    valor tipado cuando el usuario edita el campo o el registro es nuevo."""

    def __init__(self, profile: Profile, records: list[dict] | None = None,
                 raw_cells: list[dict] | None = None):
        self.profile = profile
        self.records: list[dict] = records or []
        self._raw: list[dict] = (raw_cells if raw_cells is not None
                                  else [{} for _ in self.records])

    # -- Carga -----------------------------------------------------------------
    @classmethod
    def load(cls, path: str, profile: Profile) -> "DataStore":
        encoding = "utf-8-sig" if profile.encoding.startswith("utf-8") else profile.encoding
        with open(path, "r", encoding=encoding, newline="") as f:
            grid = list(csv.reader(f, delimiter=profile.delimitador))
        if profile.orientacion == "columnas":
            records, raw_cells = cls._parse_columnas(grid, profile)
        else:
            records, raw_cells = cls._parse_filas(grid, profile)
        return cls(profile, records, raw_cells)

    @staticmethod
    def _parse_columnas(grid: list[list[str]], profile: Profile
                         ) -> tuple[list[dict], list[dict]]:
        clave = profile.campo_clave()
        if clave.fila >= len(grid):
            raise ValueError("El archivo no tiene la fila de la clave esperada "
                             f"(fila {clave.fila}).")

        # Cantidad de registros = ancho de la fila-clave, sin celdas vacías al final.
        key_row = list(grid[clave.fila])
        while key_row and key_row[-1] == "":
            key_row.pop()
        primera = profile.primera_columna_datos
        n = len(key_row) - primera

        def cell(fila: int, col: int, default: str = "") -> str:
            row = grid[fila] if fila < len(grid) else []
            return row[col] if col < len(row) else default

        ph_tmpl = profile.placeholder_template()
        records, raw_cells = [], []
        for c in range(primera, primera + n):
            rec, raw = {}, {}
            for campo in profile.campos:
                celda = cell(campo.fila, c)
                raw[campo.nombre_interno] = celda
                if campo.es_clave:
                    val = celda.strip()
                    if val == "" and ph_tmpl:
                        val = ph_tmpl.format(n=c)
                        raw[campo.nombre_interno] = val
                    rec[campo.nombre_interno] = val
                elif campo.es_numerico:
                    rec[campo.nombre_interno] = _to_number(celda, campo)
                else:
                    rec[campo.nombre_interno] = celda
            records.append(rec)
            raw_cells.append(raw)
        return records, raw_cells

    @staticmethod
    def _parse_filas(grid: list[list[str]], profile: Profile
                      ) -> tuple[list[dict], list[dict]]:
        # Mapea nombre de encabezado -> índice de columna, salvo que el campo
        # traiga 'columna' fija en el perfil.
        header = grid[profile.fila_encabezado] if profile.fila_encabezado < len(grid) else []
        header_idx = {h.strip(): i for i, h in enumerate(header)}

        def col_de(campo: Campo) -> int:
            if campo.columna is not None:
                return campo.columna
            if campo.etiqueta in header_idx:
                return header_idx[campo.etiqueta]
            raise ValueError(f"No encuentro la columna del campo "
                             f"'{campo.nombre_interno}' (etiqueta '{campo.etiqueta}').")

        cols = {c.nombre_interno: col_de(c) for c in profile.campos}
        records, raw_cells = [], []
        for row in grid[profile.primera_fila_datos:]:
            if not row or all(cell == "" for cell in row):
                continue
            rec, raw = {}, {}
            for campo in profile.campos:
                idx = cols[campo.nombre_interno]
                celda = row[idx] if idx < len(row) else ""
                raw[campo.nombre_interno] = celda
                if campo.es_clave:
                    rec[campo.nombre_interno] = celda.strip()
                elif campo.es_numerico:
                    rec[campo.nombre_interno] = _to_number(celda, campo)
                else:
                    rec[campo.nombre_interno] = celda
            records.append(rec)
            raw_cells.append(raw)
        return records, raw_cells

    # -- Serialización (fiel al formato original) ------------------------------
    def to_grid(self) -> list[list[str]]:
        if self.profile.orientacion == "columnas":
            return self._grid_columnas()
        return self._grid_filas()

    def _grid_columnas(self) -> list[list[str]]:
        p = self.profile
        n = len(self.records)
        width = p.primera_columna_datos + n

        # Determinar la última fila usada
        filas_usadas = [ff["fila"] for ff in p.filas_fijas]
        if p.fila_indice:
            filas_usadas.append(p.fila_indice["fila"])
        filas_usadas += [c.fila for c in p.campos]
        max_fila = max(filas_usadas)

        fijas = {ff["fila"]: ff for ff in p.filas_fijas}
        campos_por_fila = {c.fila: c for c in p.campos}

        grid: list[list[str]] = []
        for r in range(max_fila + 1):
            if r in fijas:
                celdas = list(fijas[r].get("celdas", []))
                if fijas[r].get("rellenar", True):
                    celdas = celdas + [""] * (width - len(celdas))
                grid.append(celdas)
            elif p.fila_indice and r == p.fila_indice["fila"]:
                base = int(p.fila_indice.get("base", 1))
                grid.append([p.fila_indice.get("etiqueta", "")] +
                            [str(base + i) for i in range(n)])
            elif r in campos_por_fila:
                campo = campos_por_fila[r]
                grid.append([campo.etiqueta] +
                            [self._cell_text(i, campo)
                             for i in range(len(self.records))])
            else:
                grid.append([""] * width)  # no debería pasar (perfil validado)
        return grid

    def _grid_filas(self) -> list[list[str]]:
        p = self.profile
        campos_ordenados = sorted(
            p.campos,
            key=lambda c: (c.columna if c.columna is not None else 1_000_000))
        header = [c.etiqueta or c.nombre_interno for c in campos_ordenados]
        grid = [header]
        for i in range(len(self.records)):
            grid.append([self._cell_text(i, c) for c in campos_ordenados])
        return grid

    def _cell_text(self, index: int, campo: Campo) -> str:
        """Texto a escribir para la celda de `campo` en el registro `index`:
        el string crudo original si la celda no fue tocada desde la carga
        (o el registro no viene de un archivo), o el valor tipado actual
        reformateado si el usuario la editó / es un registro nuevo."""
        raw = self._raw[index] if index < len(self._raw) else {}
        if campo.nombre_interno in raw:
            return raw[campo.nombre_interno]
        return _format_value(self.records[index][campo.nombre_interno], campo)

    def to_text(self) -> str:
        buf = io.StringIO()
        writer = csv.writer(buf, delimiter=self.profile.delimitador,
                            lineterminator=self.profile.fin_de_linea)
        writer.writerows(self.to_grid())
        return buf.getvalue()

    def save(self, path: str) -> None:
        encoding = "utf-8-sig" if self.profile.bom else self.profile.encoding
        with open(path, "w", encoding=encoding, newline="") as f:
            f.write(self.to_text())

    # -- CRUD ------------------------------------------------------------------
    def key_of(self, rec: dict) -> str:
        return str(rec[self.profile.campo_clave().nombre_interno]).strip()

    def nuevo_registro(self, valores: dict | None = None) -> dict:
        """Crea un registro con los defaults del perfil, pisados por `valores`."""
        rec = {}
        for c in self.profile.campos:
            rec[c.nombre_interno] = c.default if c.default is not None else (
                0 if c.es_numerico else "")
        if valores:
            rec.update(valores)
        return rec

    def add(self, rec: dict) -> dict:
        self.records.append(rec)
        self._raw.append({})  # registro nuevo: todas sus celdas se formatean
        return rec

    def update(self, index: int, valores: dict) -> None:
        self.records[index].update(valores)
        # Los campos editados dejan de usar su string crudo original: a
        # partir de ahora se reformatean desde el valor tipado (con el
        # 'formato' del campo) cada vez que se guarde.
        raw = self._raw[index]
        for k in valores:
            raw.pop(k, None)

    def delete(self, index: int) -> dict:
        self._raw.pop(index)
        return self.records.pop(index)

    def find_key(self, key: str, exclude_index: int | None = None) -> int:
        target = (key or "").strip()
        clave = self.profile.campo_clave().nombre_interno
        for i, r in enumerate(self.records):
            if i == exclude_index:
                continue
            if str(r[clave]).strip() == target:
                return i
        return -1

    # -- Placeholders (slots reservados vacíos) --------------------------------
    def is_placeholder(self, rec: dict) -> bool:
        rx = self.profile.placeholder_regex()
        if not rx:
            return False
        return bool(rx.match(self.key_of(rec)))

    def count_real(self) -> int:
        return sum(1 for r in self.records if not self.is_placeholder(r))

    # -- Detección de duplicados (según feature del perfil) --------------------
    def signature(self, key: str) -> str | None:
        cfg = self.profile.duplicados_config()
        if not cfg:
            return None
        metodo = cfg.get("metodo")
        if metodo == "ignorar_ceros":
            return key.replace("0", "")
        if metodo == "exacto":
            return key
        return None

    def find_similar_groups(self, excluded_keys: frozenset = frozenset()) -> list[list[int]]:
        """Agrupa índices de registros reales cuya firma coincide (según el
        método de duplicados del perfil). Excluye placeholders y las claves en
        `excluded_keys` (las que el usuario marcó como 'no es duplicado')."""
        if not self.profile.duplicados_config():
            return []
        groups: dict[str, list[int]] = {}
        clave = self.profile.campo_clave().nombre_interno
        for i, r in enumerate(self.records):
            if self.is_placeholder(r):
                continue
            key = str(r[clave]).strip()
            if key in excluded_keys:
                continue
            sig = self.signature(key)
            if not sig:
                continue
            groups.setdefault(sig, []).append(i)
        result = [idxs for idxs in groups.values() if len(idxs) > 1]
        result.sort(key=lambda idxs: str(self.records[idxs[0]][clave]).upper())
        return result
