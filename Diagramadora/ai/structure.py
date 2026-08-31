"""
Descubrimiento AUTOMATICO de la estructura de un archivo de ensayos.

Esta capa es 100% deterministica: NO usa inteligencia artificial.
Se encarga de lo unico que no se puede permitir que falle: leer los numeros
correctamente. La IA (ver labeler.py) se usa despues, y solamente para
ponerle nombres y unidades a lo que aca ya se descubrio.

Idea general
------------
Los equipos de laboratorio suelen escribir archivos de texto con:
  - lineas separadoras (****************)
  - lineas de metadatos/configuracion tipo  ***CLAVE=valor valor valor
  - registros de medicion que se repiten ciclicamente

En vez de programar un formato en particular, se calcula la "forma" de cada
linea (su firma), se agrupan las lineas por forma, y se detecta el ciclo que
se repite. Eso permite leer formatos nunca vistos.
"""
from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional

# ---------------------------------------------------------------------------
# Tokenizado
# ---------------------------------------------------------------------------

TOKEN_RE = re.compile(
    r"(?P<num>[+-]?\d+(?:[.,]\d+)?)"
    r"|(?P<word>[A-Za-z_ÁÉÍÓÚÑáéíóúñ]+)"
    r"|(?P<ws>[ \t]+)"
    r"|(?P<punct>[^\sA-Za-z0-9_ÁÉÍÓÚÑáéíóúñ]+)"
)


@dataclass
class Token:
    kind: str   # num | word | ws | punct
    text: str
    value: Optional[float] = None
    start: int = 0
    end: int = 0


def tokenize(line: str) -> list[Token]:
    tokens: list[Token] = []
    for m in TOKEN_RE.finditer(line):
        kind = m.lastgroup
        text = m.group()
        if kind == "num":
            try:
                value = float(text.replace(",", "."))
            except ValueError:
                value = None
            tokens.append(Token("num", text, value, m.start(), m.end()))
        else:
            tokens.append(Token(kind, text, None, m.start(), m.end()))
    return tokens


def signature(tokens: list[Token]) -> str:
    """Forma normalizada de la linea: los numeros pasan a ser N y las palabras W."""
    out = []
    for t in tokens:
        if t.kind == "num":
            out.append("N")
        elif t.kind == "word":
            out.append("W")
        elif t.kind == "ws":
            out.append(" ")
        else:
            out.append(t.text)
    return "".join(out).strip()


def _meaningful(tokens: list[Token]) -> list[Token]:
    return [t for t in tokens if t.kind != "ws"]


# ---------------------------------------------------------------------------
# Clasificacion de lineas
# ---------------------------------------------------------------------------

LINE_BLANK = "blank"
LINE_DELIM = "delim"
LINE_META = "meta"     # linea de configuracion / cabecera
LINE_DATA = "data"

ASSIGN_CHARS = ("=", ":")


@dataclass
class ClassifiedLine:
    index: int
    raw: str
    tokens: list[Token]
    sig: str
    kind: str


def _is_pure_punct(tokens: list[Token]) -> bool:
    mf = _meaningful(tokens)
    return bool(mf) and all(t.kind == "punct" for t in mf)


def _has_meta_prefix(tokens: list[Token]) -> bool:
    """Lineas que arrancan con un prefijo de comentario/metadato: ***, ##, //, ;"""
    mf = _meaningful(tokens)
    if not mf or mf[0].kind != "punct":
        return False
    p = mf[0].text
    return len(p) >= 2 or p in ("#", ";", "*", "!")


def _looks_like_assignment(tokens: list[Token]) -> bool:
    """Detecta lineas tipo  CLAVE= 1 2 3  o  CLAVE: 12.5 mm

    Una hora (09:12:33) no se confunde con una asignacion porque antes de los
    dos puntos hay un numero, no una palabra.
    """
    mf = _meaningful(tokens)
    for i, t in enumerate(mf[:-1]):
        if t.kind == "word":
            nxt = mf[i + 1]
            if nxt.kind == "punct" and any(c in nxt.text for c in ASSIGN_CHARS):
                return True
    return False


def _is_section_header(tokens: list[Token]) -> bool:
    """Lineas tipo [CONFIGURACION] o [DATOS], que solo marcan una seccion."""
    mf = _meaningful(tokens)
    if len(mf) < 3:
        return False
    return (mf[0].kind == "punct" and "[" in mf[0].text
            and mf[-1].kind == "punct" and "]" in mf[-1].text
            and not any(t.kind == "num" for t in mf))


def classify_line(index: int, raw: str) -> ClassifiedLine:
    tokens = tokenize(raw)
    sig = signature(tokens)

    if not raw.strip():
        return ClassifiedLine(index, raw, tokens, sig, LINE_BLANK)
    if _is_pure_punct(tokens) or _is_section_header(tokens):
        return ClassifiedLine(index, raw, tokens, sig, LINE_DELIM)
    if _has_meta_prefix(tokens) or _looks_like_assignment(tokens):
        return ClassifiedLine(index, raw, tokens, sig, LINE_META)
    return ClassifiedLine(index, raw, tokens, sig, LINE_DATA)


# ---------------------------------------------------------------------------
# Fechas y horas
# ---------------------------------------------------------------------------


def _digits(text: str) -> int:
    return len(text.strip("+-").replace(".", "").replace(",", ""))


@dataclass
class FieldValue:
    name: str
    value: object
    kind: str  # number | flag | datetime | date | time


def _classify_triplet(toks: list[Token]) -> str:
    """Decide si un grupo N:N:N es una fecha o una hora."""
    a, b, c = (t.value for t in toks)
    # un año se reconoce por tener 4 digitos
    if any(_digits(t.text) == 4 for t in toks):
        return "date"
    if a is not None and b is not None and c is not None:
        if a <= 24 and b <= 59 and c <= 59:
            return "time"
    return "date"


def _safe_datetime(d: Optional[list[float]], t: Optional[list[float]]) -> Optional[datetime]:
    try:
        hh = mm = ss = 0
        if t:
            hh, mm, ss = int(t[0]), int(t[1]), int(t[2])
        if d is None:
            return None
        a, b, c = int(d[0]), int(d[1]), int(d[2])
        if c > 31:
            day, month, year = a, b, c
        elif a > 31:
            year, month, day = a, b, c
        else:
            day, month, year = a, b, c
        return datetime(year, month, day, hh, mm, ss)
    except (ValueError, TypeError, IndexError):
        return None


def _detect_datetime_groups(tokens: list[Token]) -> tuple[list[FieldValue], set[int]]:
    """Detecta grupos N:N:N (fecha u hora) y los devuelve como campos."""
    fields: list[FieldValue] = []
    consumed: set[int] = set()
    mf = _meaningful(tokens)
    pos = [i for i, t in enumerate(tokens) if t.kind != "ws"]

    groups: list[tuple[list[Token], list[int]]] = []
    i = 0
    while i <= len(mf) - 5:
        if (
            mf[i].kind == "num"
            and mf[i + 1].kind == "punct" and mf[i + 1].text in (":", "/", "-", ".")
            and mf[i + 2].kind == "num"
            and mf[i + 3].kind == "punct" and mf[i + 3].text == mf[i + 1].text
            and mf[i + 4].kind == "num"
        ):
            toks = [mf[i], mf[i + 2], mf[i + 4]]
            idxs = [pos[i], pos[i + 1], pos[i + 2], pos[i + 3], pos[i + 4]]
            groups.append((toks, idxs))
            i += 5
        else:
            i += 1

    if not groups:
        return fields, consumed

    parsed: list[tuple[str, list[Token]]] = []
    for toks, idxs in groups:
        parsed.append((_classify_triplet(toks), toks))
        consumed.update(idxs)

    kinds = [k for k, _ in parsed]
    if len(parsed) == 2 and kinds[0] == "date" and kinds[1] == "time":
        d = [t.value for t in parsed[0][1]]
        t = [t.value for t in parsed[1][1]]
        fields.append(FieldValue("timestamp", _safe_datetime(d, t), "datetime"))
    else:
        for kind, toks in parsed:
            vals = [t.value for t in toks]
            if kind == "date":
                fields.append(FieldValue("date", _safe_datetime(vals, None), "date"))
            else:
                fields.append(FieldValue(
                    "time", f"{int(vals[0]):02d}:{int(vals[1]):02d}:{int(vals[2]):02d}", "time"
                ))
    return fields, consumed


# ---------------------------------------------------------------------------
# Extraccion de campos de una linea de datos
# ---------------------------------------------------------------------------


def extract_fields(tokens: list[Token]) -> list[FieldValue]:
    """Extrae campos con nombre de una linea de datos.

    Patrones tipicos de estos equipos:
      E690   -> campo 'E' con valor 690   (letra pegada a numero)
      C-86   -> campo 'C' con valor -86
      Y+     -> bandera 'Y' con valor '+'
      125    -> numero suelto -> 'n0', 'n1', ...
      18:5:2018 17:59:42 -> timestamp
    """
    fields, consumed = _detect_datetime_groups(tokens)

    n_index = 0
    t_index = 0
    i = 0
    while i < len(tokens):
        if i in consumed:
            i += 1
            continue
        t = tokens[i]
        if t.kind == "ws":
            i += 1
            continue

        if t.kind == "word":
            if i + 1 < len(tokens) and tokens[i + 1].kind == "num":
                fields.append(FieldValue(t.text, tokens[i + 1].value, "number"))
                consumed.add(i + 1)
                i += 2
                continue
            if (i + 1 < len(tokens) and tokens[i + 1].kind == "punct"
                    and tokens[i + 1].text in ("+", "-")):
                fields.append(FieldValue(t.text, tokens[i + 1].text, "flag"))
                consumed.add(i + 1)
                i += 2
                continue
            # palabra suelta: suele ser un resultado (OK / NOK / PASS / FALLA)
            fields.append(FieldValue(f"txt{t_index}", t.text, "text"))
            t_index += 1
            i += 1
            continue

        if t.kind == "num":
            fields.append(FieldValue(f"n{n_index}", t.value, "number"))
            n_index += 1
            i += 1
            continue

        i += 1

    return fields


# ---------------------------------------------------------------------------
# Parseo de lineas de metadatos / configuracion
# ---------------------------------------------------------------------------


@dataclass
class ConfigEntry:
    key: str
    numbers: list
    text: str
    raw: str
    line_index: int


def _read_key(mf: list[Token], i: int) -> tuple[Optional[str], int]:
    """Lee una clave que puede incluir corchetes:  FZA[VEL]  ->  ('FZA[VEL]', j)."""
    if i >= len(mf) or mf[i].kind != "word":
        return None, i
    parts = [mf[i].text]
    j = i + 1
    while j < len(mf) and mf[j].kind == "punct" and mf[j].text in ("[", "_", "."):
        if j + 1 < len(mf) and mf[j + 1].kind == "word":
            parts.append(mf[j].text)
            parts.append(mf[j + 1].text)
            j += 2
            if j < len(mf) and mf[j].kind == "punct" and mf[j].text == "]":
                parts.append("]")
                j += 1
        else:
            break
    return "".join(parts), j


def parse_config_line(cl: ClassifiedLine) -> list[ConfigEntry]:
    """Convierte una linea de metadatos en una o varias entradas clave -> valores.

    Soporta:
      ***VELOC=125  31  0        -> VELOC = [125, 31, 0]
      ***ARCHIVO= x  CARRERA= 80 -> dos entradas en la misma linea
      ***FZA[VEL] 70 mm/s 278 Kg -> sin '=', la primera palabra es la clave
      ***18:5:2018  17:42:25     -> sin clave: se guarda como '_timestamp'
    """
    mf = _meaningful(cl.tokens)
    if mf and mf[0].kind == "punct":
        mf = mf[1:]
    if not mf:
        return []

    # linea de metadatos que en realidad es una fecha/hora
    dt_fields, _ = _detect_datetime_groups(cl.tokens)
    if dt_fields and not any(t.kind == "word" for t in mf):
        out = []
        for f in dt_fields:
            out.append(ConfigEntry(f"_{f.name}", [], str(f.value), cl.raw.strip(), cl.index))
        return out

    # ubicar las claves (palabra seguida de '=' o ':')
    key_positions: list[tuple[int, int, str]] = []
    i = 0
    while i < len(mf):
        if mf[i].kind == "word":
            key, j = _read_key(mf, i)
            if key and j < len(mf) and mf[j].kind == "punct" and any(
                c in mf[j].text for c in ASSIGN_CHARS
            ):
                key_positions.append((i, j + 1, key))
                i = j + 1
                continue
        i += 1

    entries: list[ConfigEntry] = []

    def _segment_text(seg: list[Token]) -> str:
        """Texto original del tramo, respetando los espacios del archivo."""
        if not seg:
            return ""
        return cl.raw[seg[0].start:seg[-1].end].strip()

    if key_positions:
        for idx, (start, val_start, key) in enumerate(key_positions):
            end = key_positions[idx + 1][0] if idx + 1 < len(key_positions) else len(mf)
            seg = mf[val_start:end]
            numbers = [t.value for t in seg if t.kind == "num" and t.value is not None]
            entries.append(ConfigEntry(key, numbers, _segment_text(seg),
                                       cl.raw.strip(), cl.index))
        return entries

    # sin '=': la primera palabra es la clave y el resto son valores
    key, j = _read_key(mf, 0)
    if key:
        seg = mf[j:]
        numbers = [t.value for t in seg if t.kind == "num" and t.value is not None]
        entries.append(ConfigEntry(key, numbers, _segment_text(seg),
                                   cl.raw.strip(), cl.index))
    return entries


# ---------------------------------------------------------------------------
# Deteccion del ciclo de registro
# ---------------------------------------------------------------------------


def detect_period(seq: list[str], max_period: int = 30) -> tuple[int, float]:
    n = len(seq)
    if n < 4:
        return 1, 0.0
    best_p, best_score = 1, 0.0
    limit = min(max_period, n // 2)
    for p in range(1, limit + 1):
        matches = sum(1 for i in range(n - p) if seq[i] == seq[i + p])
        score = matches / (n - p)
        if score > best_score + 1e-9:
            best_p, best_score = p, score
    return best_p, best_score


# ---------------------------------------------------------------------------
# Resultado
# ---------------------------------------------------------------------------


@dataclass
class ConfigSnapshot:
    index: int
    line_index: int
    entries: dict
    raw_lines: list
    n_records: int = 0


@dataclass
class Record:
    number: int
    config_index: Optional[int]
    fields: dict
    line_start: int


@dataclass
class Discovery:
    config_snapshots: list
    records: list
    record_field_names: list
    config_keys: list
    period: int
    period_score: float
    line_kind_counts: dict
    unparsed_lines: list
    total_lines: int
    record_start_signature: Optional[str]


def _field_key(base: str, seen: Counter) -> str:
    seen[base] += 1
    if seen[base] == 1:
        return base
    return f"{base}_{seen[base]}"


def discover(lines: list[str], progress_callback=None) -> Discovery:
    total = len(lines)
    classified: list[ClassifiedLine] = []
    report_every = max(1, total // 100)
    for i, raw in enumerate(lines):
        if progress_callback and i % report_every == 0:
            progress_callback(i, total)
        classified.append(classify_line(i, raw.rstrip("\n").rstrip("\r")))

    kind_counts = Counter(c.kind for c in classified)

    # ---- inicio de registro: la firma que mas veces arranca despues de un corte
    after_break = Counter()
    prev_non_data = True
    for c in classified:
        if c.kind == LINE_DATA:
            if prev_non_data:
                after_break[c.sig] += 1
            prev_non_data = False
        else:
            prev_non_data = True

    data_sigs = [c.sig for c in classified if c.kind == LINE_DATA]
    period, score = detect_period(data_sigs)

    start_sig = None
    if after_break:
        top_sig, top_count = after_break.most_common(1)[0]
        # confiable solo si esa firma arranca la gran mayoria de los registros
        if top_count >= 5:
            start_sig = top_sig
    if start_sig is None and data_sigs:
        start_sig = Counter(data_sigs).most_common(1)[0][0]

    # ---- recorrido principal
    snapshots: list[ConfigSnapshot] = []
    current_entries: dict = {}
    records: list[Record] = []
    field_names_order: list[str] = []
    field_names_seen: set[str] = set()
    unparsed: list[tuple[int, str]] = []

    cur_fields: dict = {}
    cur_seen: Counter = Counter()
    cur_start_line = 0
    have_record = False
    data_since_snapshot = False

    def flush_record():
        nonlocal cur_fields, cur_seen, have_record
        if have_record and cur_fields:
            records.append(Record(
                number=len(records) + 1,
                config_index=(snapshots[-1].index if snapshots else None),
                fields=cur_fields,
                line_start=cur_start_line,
            ))
            if snapshots:
                snapshots[-1].n_records += 1
        cur_fields = {}
        cur_seen = Counter()
        have_record = False

    for c in classified:
        if c.kind == LINE_BLANK:
            continue

        if c.kind == LINE_DELIM:
            continue

        if c.kind == LINE_META:
            # Un bloque nuevo empieza cuando hubo mediciones desde el bloque
            # anterior. Los bloques consecutivos (separados solo por lineas
            # de asteriscos) se consideran uno solo: el ultimo pisa al anterior.
            if data_since_snapshot or not snapshots:
                flush_record()
                current_entries = dict(current_entries)
                snapshots.append(ConfigSnapshot(
                    index=len(snapshots) + 1,
                    line_index=c.index,
                    entries=current_entries,
                    raw_lines=[],
                ))
                data_since_snapshot = False
            for e in parse_config_line(c):
                current_entries[e.key] = e
            snapshots[-1].entries = dict(current_entries)
            snapshots[-1].raw_lines.append(c.raw.strip())
            continue

        # linea de datos
        data_since_snapshot = True
        if start_sig is not None and c.sig == start_sig:
            flush_record()
            cur_start_line = c.index
            have_record = True
        if not have_record:
            have_record = True
            cur_start_line = c.index

        fvs = extract_fields(c.tokens)
        if not fvs:
            unparsed.append((c.index, c.raw))
            continue
        for fv in fvs:
            name = _field_key(fv.name, cur_seen)
            cur_fields[name] = fv.value
            if name not in field_names_seen:
                field_names_seen.add(name)
                field_names_order.append(name)

    flush_record()

    config_keys: list[str] = []
    for snap in snapshots:
        for k in snap.entries:
            if k not in config_keys:
                config_keys.append(k)

    if progress_callback:
        progress_callback(total, total)

    return Discovery(
        config_snapshots=snapshots,
        records=records,
        record_field_names=field_names_order,
        config_keys=config_keys,
        period=period,
        period_score=score,
        line_kind_counts=dict(kind_counts),
        unparsed_lines=unparsed[:50],
        total_lines=total,
        record_start_signature=start_sig,
    )


def read_text_file(path: str) -> list[str]:
    for enc in ("utf-8-sig", "cp1252", "latin-1"):
        try:
            with open(path, encoding=enc) as f:
                return f.readlines()
        except UnicodeDecodeError:
            continue
    with open(path, encoding="latin-1", errors="replace") as f:
        return f.readlines()
