"""Reporte de salud del catálogo (Nivel 4.5 del plan de mejoras).

Junta en una sola pasada, sin abrir ninguna ventana, los problemas que
antes solo se descubrían uno por uno (al editar, al importar, al buscar
duplicados a mano): valores fuera de rango, códigos con posibles
duplicados sin revisar, campos obligatorios vacíos, y cuántos slots libres
(placeholders) quedan disponibles."""

from __future__ import annotations

from dataclasses import dataclass

from datastore import DataStore
from metadata import Sidecar
import validacion


@dataclass
class Hallazgo:
    tipo: str        # "fuera_de_rango" | "duplicado" | "campo_vacio"
    idx: int          # índice del registro en store.records (para poder ir directo)
    code: str
    mensaje: str


def evaluar_salud(store: DataStore, sidecar: Sidecar) -> list[Hallazgo]:
    profile = store.profile
    hallazgos: list[Hallazgo] = []

    reales = [(i, r) for i, r in enumerate(store.records) if not store.is_placeholder(r)]

    # -- valores fuera de rango -------------------------------------------------
    for i, r in reales:
        errores = validacion.validar_valores_de_registro(profile, r)
        for err in errores:
            hallazgos.append(Hallazgo("fuera_de_rango", i, store.key_of(r), err.mensaje))

    # -- campos obligatorios vacíos ----------------------------------------------
    for c in profile.campos_visibles():
        if c.es_clave:
            continue
        for i, r in reales:
            valor = r.get(c.nombre_interno)
            vacio = valor is None or (isinstance(valor, str) and not valor.strip())
            if vacio:
                hallazgos.append(Hallazgo(
                    "campo_vacio", i, store.key_of(r),
                    f"«{c.titulo_ui}» está vacío."))

    # -- duplicados sin revisar (según feature del perfil) ----------------------
    if profile.duplicados_config():
        excluded = sidecar.keys_with("no_duplicado")
        grupos = store.find_similar_groups(excluded_keys=excluded)
        for grupo in grupos:
            for i in grupo:
                r = store.records[i]
                hallazgos.append(Hallazgo(
                    "duplicado", i, store.key_of(r),
                    "Código parecido a otro(s) del catálogo, sin revisar."))

    hallazgos.sort(key=lambda h: (h.tipo, h.code.upper()))
    return hallazgos


def contar_slots_libres(store: DataStore) -> int:
    """Placeholders (slots reservados vacíos) disponibles para nuevos
    registros — 0 si el perfil no usa placeholders."""
    if store.profile.placeholder_regex() is None:
        return 0
    return sum(1 for r in store.records if store.is_placeholder(r))
