"""Cálculo de diferencias entre el catálogo cargado y filas leídas de un
Excel de importación. Extraído de ImportDialog._compute_diffs (Nivel 3.1)
para poder probarlo sin abrir ninguna ventana."""

from __future__ import annotations

import excel_import
import validacion
from datastore import DataStore
from profile import Profile


def calcular_diferencias(store: DataStore, profile: Profile,
                          mapped_fields: set[str], rows: list[dict]):
    """Compara `rows` (ya leídas del Excel, sin normalizar) contra
    `store.records`. Devuelve (diffs, new_records, obsolete, unchanged):

    - diffs: registros existentes cuyos parámetros mapeados difieren. Cada
      uno incluye "redondeos": nombres de campos enteros donde la celda del
      Excel tenía decimales y se redondeó en silencio (Nivel 4.6).
    - new_records: códigos del Excel que no están en el catálogo (también
      con "redondeos").
    - obsolete: registros del catálogo (no placeholders) cuyo código no
      apareció en el Excel.
    - unchanged: cantidad de registros existentes que coinciden sin cambios.
    """
    CAMPOS_ENTEROS = {"entero", "entero_ceros"}
    clave = profile.campo_clave()
    params = profile.parametros_visibles()
    campos_mapeados = [c for c in profile.campos_visibles()
                       if c.nombre_interno in mapped_fields]
    by_index: dict[int, dict] = {}
    matched_indices: set[int] = set()
    new_by_code: dict[str, dict] = {}
    unchanged = 0

    for raw in rows:
        code = excel_import.normalize_code(raw.get(clave.nombre_interno))
        if not code:
            continue
        idx = store.find_key(code)

        if idx == -1:
            # Código del Excel que no existe en el catálogo: candidato a
            # registro nuevo. Se toman todos los campos mapeados (no solo
            # los parámetros) para poder crearlo completo.
            valores = {c.nombre_interno: excel_import.normalize_value(
                          raw.get(c.nombre_interno), c.tipo)
                      for c in campos_mapeados}
            valores[clave.nombre_interno] = code
            errores = validacion.validar_valores_de_registro(profile, valores)
            redondeos = [c.nombre_interno for c in campos_mapeados
                        if c.tipo in CAMPOS_ENTEROS
                        and excel_import.tuvo_decimales(raw.get(c.nombre_interno))]
            new_by_code[code] = {"code": code, "valores": valores, "errores": errores,
                                 "redondeos": redondeos}
            continue

        matched_indices.add(idx)
        rec = store.records[idx]
        old_vals, new_vals, differs = {}, {}, False
        for c in params:
            nv = excel_import.normalize_value(raw.get(c.nombre_interno), c.tipo)
            old_vals[c.nombre_interno] = rec[c.nombre_interno]
            new_vals[c.nombre_interno] = nv
            if nv is not None and nv != rec[c.nombre_interno]:
                differs = True
        if differs:
            # Los valores fuera de rango del perfil (min/max) se detectan
            # acá también: antes solo se validaban al editar a mano
            # (RecordDialog), y un typo en el Excel entraba sin control.
            errores = validacion.validar_valores_de_registro(profile, new_vals)
            redondeos = [c.nombre_interno for c in params
                        if c.tipo in CAMPOS_ENTEROS
                        and excel_import.tuvo_decimales(raw.get(c.nombre_interno))]
            by_index[idx] = {"idx": idx, "code": store.key_of(rec),
                             "old": old_vals, "new": new_vals, "errores": errores,
                             "redondeos": redondeos}
        else:
            unchanged += 1

    diffs = sorted(by_index.values(), key=lambda d: d["code"].upper())
    new_records = sorted(new_by_code.values(), key=lambda d: d["code"].upper())

    # Registros que están en el catálogo actual (no placeholders) pero
    # cuyo código no apareció en el Excel: candidatos a obsoletos.
    obsolete = []
    for i, r in enumerate(store.records):
        if i in matched_indices or store.is_placeholder(r):
            continue
        obsolete.append({"idx": i, "code": store.key_of(r)})
    obsolete.sort(key=lambda d: d["code"].upper())

    return diffs, new_records, obsolete, unchanged
