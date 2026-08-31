"""
Capa SEMANTICA: le pone nombre y unidad a los campos que descubrio structure.py.

Esta es la unica parte donde interviene la IA, y esta acotada a proposito:
  - La IA NO lee los datos ni toca ningun numero.
  - La IA NO decide como se parsea el archivo.
  - La IA solo mira el archivo CON ANOTACIONES (el que escribe el tecnico) y
    propone un nombre y una unidad para cada campo ya descubierto.

Si la IA no esta disponible, falla, o responde cualquier cosa, el programa
sigue funcionando igual: se usan los nombres crudos del equipo. Es decir, la
IA mejora el resultado pero nunca es imprescindible.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Optional

import llm


MAX_ANNOTATED_CHARS = 6000
SAFE_LABEL_RE = re.compile(r"[^\wÁÉÍÓÚÑáéíóúñ ()%/.,+-]")


@dataclass
class Label:
    key: str
    label: str
    unit: str = ""
    source: str = "auto"   # ia | auto


@dataclass
class LabelSet:
    config: dict = field(default_factory=dict)   # key -> Label
    fields: dict = field(default_factory=dict)   # key -> Label
    used_ai: bool = False
    messages: list = field(default_factory=list)
    seconds: float = 0.0

    def config_label(self, key: str) -> Label:
        return self.config.get(key) or Label(key, key)

    def field_label(self, key: str) -> Label:
        return self.fields.get(key) or Label(key, key)


def _clean(text: str, limit: int = 48) -> str:
    text = SAFE_LABEL_RE.sub("", str(text)).strip()
    text = re.sub(r"\s+", " ", text)
    return text[:limit].strip()


# palabras que el modelo suele poner cuando en realidad no hay unidad
NON_UNITS = {
    "no", "n/a", "na", "ninguna", "ninguno", "sin unidad", "sin",
    "none", "-", "signo", "adimensional", "texto", "valor",
}


def _clean_unit(text: str) -> str:
    u = _clean(text, 16)
    if u.lower().strip(". ") in NON_UNITS:
        return ""
    return u


def _disambiguate(labels: dict) -> None:
    """Red de seguridad deterministica sobre lo que propuso la IA.

    Los modelos chicos tienden a repetir la misma etiqueta para campos que en
    realidad son distintos (por ejemplo E y E_2, que son la misma magnitud pero
    a otra velocidad de ensayo). Aca se arregla sin volver a preguntarle al
    modelo: a los campos con sufijo _N se les agrega el numero, y si aun asi
    quedan etiquetas repetidas se les agrega la clave original del equipo.
    """
    # 1. los campos con sufijo _2 / _3 llevan el numero en el nombre
    for key, lb in labels.items():
        m = re.search(r"_(\d+)$", key)
        if m and not re.search(r"\d\s*$", lb.label):
            lb.label = f"{lb.label} {m.group(1)}"

    # 2. si todavia hay repetidos, se agrega la clave original
    counts: dict[str, list] = {}
    for key, lb in labels.items():
        counts.setdefault(lb.label.lower(), []).append(key)
    for label_text, keys in counts.items():
        if len(keys) > 1:
            for key in keys:
                labels[key].label = f"{labels[key].label} [{key}]"


def _sample_text(value) -> str:
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value)


def _describe_config_keys(discovery, limit: int = 24) -> list[tuple[str, str]]:
    out: list[tuple[str, str]] = []
    seen: set[str] = set()
    for snap in discovery.config_snapshots:
        for key, entry in snap.entries.items():
            if key in seen:
                continue
            seen.add(key)
            if entry.numbers:
                sample = ", ".join(_sample_text(v) for v in entry.numbers[:6])
            else:
                sample = entry.text[:40]
            out.append((key, sample))
            if len(out) >= limit:
                return out
    return out


def _describe_record_fields(discovery, limit: int = 24) -> list[tuple[str, str]]:
    out: list[tuple[str, str]] = []
    samples: dict[str, list[str]] = {}
    for rec in discovery.records[:200]:
        for k, v in rec.fields.items():
            samples.setdefault(k, [])
            if len(samples[k]) < 3:
                samples[k].append(_sample_text(v))
    for name in discovery.record_field_names[:limit]:
        out.append((name, ", ".join(samples.get(name, []))))
    return out


SYSTEM_PROMPT = (
    "Sos un asistente tecnico que documenta archivos generados por maquinas de "
    "ensayo industriales. Respondes unicamente en JSON, en español, sin explicaciones."
)


def _find_hint(key: str, annotated_text: str) -> str:
    """Busca en el archivo anotado la linea donde aparece esa clave."""
    if len(key) < 3:
        return ""      # claves de 1-2 letras dan demasiados falsos positivos
    for line in annotated_text.splitlines():
        if key.lower() in line.lower():
            return line.strip()[:160]
    return ""


def _build_user_prompt(
    annotated_text: Optional[str], items: list[tuple[str, str]], que_son: str
) -> str:
    """Arma el prompt. Hay dos modos:

    - CON anotaciones: la IA solo puede usar lo que el tecnico escribio.
    - SIN anotaciones (por ejemplo un CSV donde los propios nombres de columna
      ya son autoexplicativos, como PRESION_NOMINAL o CAUDAL_LPM): la IA
      humaniza esos nombres crudos, sin inventar informacion que no este en
      la propia clave.
    """
    partes = []
    for k, s in items:
        hint = _find_hint(k, annotated_text) if annotated_text else ""
        linea = f"- {k}   (valores de ejemplo: {s})"
        if hint:
            linea += f"\n    linea del archivo anotado: {hint}"
        partes.append(linea)
    lineas = "\n".join(partes)

    if annotated_text:
        anotado = annotated_text.strip()
        if len(anotado) > MAX_ANNOTATED_CHARS:
            anotado = anotado[:MAX_ANNOTATED_CHARS] + "\n[...]"
        return (
            "Una maquina de ensayos genera archivos de texto. Un tecnico escribio una "
            "version del archivo CON ANOTACIONES entre parentesis, explicando que "
            "significa cada valor.\n\n"
            "=== ARCHIVO CON ANOTACIONES ===\n"
            f"{anotado}\n\n"
            f"=== {que_son} ===\n"
            f"{lineas}\n\n"
            "Para CADA campo indica:\n"
            '  "label": nombre corto y claro en español de QUE ES ese campo.\n'
            '  "unit": la unidad de medida.\n\n'
            "REGLAS IMPORTANTES:\n"
            "1. Usa UNICAMENTE lo que dicen las anotaciones. No inventes ni supongas.\n"
            "2. Si un campo NO esta explicado en las anotaciones, poné como label el "
            'mismo nombre del campo y como unit "".\n'
            "3. La unidad tiene que ser una que aparezca en las anotaciones "
            '(por ejemplo kgf, mm/s, mm). Si no aparece ninguna, poné "".\n'
            "4. Si un campo es una bandera con valores + o -, la unidad es \"\".\n"
            "5. Los campos terminados en _2 o _3 son la MISMA magnitud repetida para "
            "otra velocidad de ensayo: usa el mismo nombre agregando el numero.\n"
            "6. Campos distintos deben tener nombres distintos.\n\n"
            "Responde solo el JSON."
        )

    # sin archivo de anotaciones: humanizar los nombres crudos
    return (
        "Un equipo de ensayos genera archivos de texto o CSV donde los nombres de "
        "los campos y parametros ya son bastante descriptivos por si solos (por "
        "ejemplo PRESION_NOMINAL o CAUDAL_LPM). No hay archivo de anotaciones.\n\n"
        "EJEMPLO de la transformacion esperada:\n"
        '  PRESION_NOMINAL_BAR   ->  label: "Presion nominal"   unit: "bar"\n'
        '  CAUDAL_MAX_LPM        ->  label: "Caudal maximo"     unit: "lpm"\n'
        '  TEMPERATURA_C         ->  label: "Temperatura"       unit: "C"\n'
        '  ID_LOTE               ->  label: "Id lote"           unit: ""\n'
        "Notar que la unidad se SACA del nombre del campo y no se repite en el "
        "label; el label queda en Oracion normal (solo la primera letra en "
        "mayuscula), sin guiones bajos.\n\n"
        f"=== {que_son} ===\n"
        f"{lineas}\n\n"
        "Para CADA campo indica:\n"
        '  "label": el nombre humanizado, siguiendo el ejemplo de arriba.\n'
        '  "unit": la unidad de medida SOLO SI esta explicita en el propio nombre. '
        'Si el nombre no trae ninguna unidad, dejala en "".\n\n'
        "REGLAS IMPORTANTES:\n"
        "1. NO inventes que mide un campo si el nombre no lo dice. Ante la duda, "
        "limitate a prolijar el nombre tal cual esta.\n"
        "2. No inventes una unidad que no este escrita en el nombre del campo.\n"
        "3. Los campos terminados en _2 o _3 son la MISMA magnitud repetida para "
        "otra velocidad o canal de ensayo: usa el mismo nombre agregando el numero.\n"
        "4. Campos distintos deben tener nombres distintos.\n\n"
        "Responde solo el JSON."
    )


def _run_group(
    annotated_text: Optional[str],
    items: list[tuple[str, str]],
    que_son: str,
    progress_callback=None,
) -> tuple[dict, str, float]:
    if not items:
        return {}, "", 0.0

    keys = [k for k, _ in items]
    grammar = llm.build_labeling_grammar(keys)
    user = _build_user_prompt(annotated_text, items, que_son)

    res = llm.run_llm(
        SYSTEM_PROMPT,
        user,
        grammar=grammar,
        max_tokens=64 * len(keys) + 128,
        progress_callback=progress_callback,
    )
    if not res.ok:
        return {}, res.error, res.seconds

    data = llm.extract_json(res.text)
    if not isinstance(data, list):
        return {}, "La IA no devolvio una lista JSON valida.", res.seconds

    valid_keys = set(keys)
    out: dict[str, Label] = {}
    for item in data:
        if not isinstance(item, dict):
            continue
        k = item.get("key")
        if k not in valid_keys:
            continue          # la IA no puede inventar campos
        label = _clean(item.get("label", ""))
        unit = _clean_unit(item.get("unit", ""))
        if not label:
            continue
        out[k] = Label(k, label, unit, "ia")
    return out, "", res.seconds


def build_labels(
    discovery,
    annotated_text: Optional[str],
    use_ai: bool = True,
    progress_callback=None,
) -> LabelSet:
    """Arma las etiquetas de todos los campos. La IA es opcional."""
    result = LabelSet()

    config_items = _describe_config_keys(discovery)
    field_items = _describe_record_fields(discovery)

    # valores por defecto: el nombre crudo del equipo
    for k, _ in config_items:
        result.config[k] = Label(k, k, "", "auto")
    for k, _ in field_items:
        result.fields[k] = Label(k, k, "", "auto")

    if not use_ai:
        result.messages.append("IA desactivada: se usan los nombres originales del equipo.")
        return result

    if not annotated_text:
        result.messages.append(
            "No se cargo archivo con anotaciones: la IA va a prolijar los nombres "
            "que ya trae el equipo, sin adivinar unidades ni significados que no "
            "esten escritos en esos nombres."
        )

    ok, msg = llm.is_available()
    if not ok:
        result.messages.append(f"{msg} Se usan los nombres originales del equipo.")
        return result

    total_seconds = 0.0

    if progress_callback:
        progress_callback("Interpretando los parametros de configuracion...", 0.0)
    cfg_labels, err, secs = _run_group(
        annotated_text, config_items, "PARAMETROS DE CONFIGURACION DEL ENSAYO",
        progress_callback=(lambda t: progress_callback(
            "Interpretando los parametros de configuracion...", t)) if progress_callback else None,
    )
    total_seconds += secs
    if err:
        result.messages.append(f"Configuracion: {err}")
    result.config.update(cfg_labels)

    if progress_callback:
        progress_callback("Interpretando los campos de cada medicion...", 0.0)
    fld_labels, err2, secs2 = _run_group(
        annotated_text, field_items, "CAMPOS DE CADA MEDICION",
        progress_callback=(lambda t: progress_callback(
            "Interpretando los campos de cada medicion...", t)) if progress_callback else None,
    )
    total_seconds += secs2
    if err2:
        result.messages.append(f"Mediciones: {err2}")
    result.fields.update(fld_labels)

    # red de seguridad: arreglar etiquetas repetidas sin volver a usar la IA
    _disambiguate(result.config)
    _disambiguate(result.fields)

    result.seconds = total_seconds
    result.used_ai = bool(cfg_labels or fld_labels)
    if result.used_ai:
        n = len(cfg_labels) + len(fld_labels)
        result.messages.append(f"La IA local nombro {n} campos en {total_seconds:.0f}s.")
    else:
        result.messages.append(
            "La IA local no pudo interpretar los campos: se usan los nombres originales."
        )
    return result
