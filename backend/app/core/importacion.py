"""Cálculo de diferencias entre el catálogo cargado y filas leídas de un
Excel de importación.

El cruce se hace por una **clave de búsqueda** elegida en la importación
(un campo visible del perfil, sin el ID automático). No tiene por qué ser la
PK: con ID automático, la PK no viene en el archivo de la máquina.

- Una clave repetida en el Excel, o en el catálogo, es un **conflicto**: no
  se importa ninguna de esas filas hasta corregir el dato.
- Una clave del Excel que no está en el catálogo es solo un **aviso**: no se
  crea ningún registro (lo carga el ingeniero).
- Una celda vacía del Excel no cuenta como cambio.
"""

from __future__ import annotations

import excel_import
import validacion
from datastore import DataStore
from profile import Profile

CAMPOS_ENTEROS = {"entero", "entero_ceros"}


def clave_busqueda(valor, tipo: str) -> str:
    """Valor canónico para comparar. Sirve igual para una celda cruda del Excel
    y para un valor tipado del catálogo: `"0012"` y `12` dan la misma clave en
    campos numéricos; en texto solo se recortan espacios y el ".0" de Excel.
    Vacío si no hay dato."""
    if tipo == "decimal":
        d = excel_import.normalize_decimal(valor)
        if d is not None:
            return repr(d)
    elif tipo in CAMPOS_ENTEROS:
        n = excel_import.normalize_int(valor)
        if n is not None:
            return str(n)
    return excel_import.normalize_code(valor)


def indice_por_busqueda(store: DataStore, profile: Profile, campo: str) -> dict[str, list[int]]:
    """{clave_busqueda: [índices de registros]}. Una clave con más de un
    índice es un conflicto; las claves vacías no se indexan."""
    tipo = profile.campo_por_nombre(campo).tipo
    indice: dict[str, list[int]] = {}
    for i, rec in enumerate(store.records):
        clave = clave_busqueda(rec.get(campo), tipo)
        if clave:
            indice.setdefault(clave, []).append(i)
    return indice


def _es_placeholder(profile: Profile, rec: dict, campo: str) -> bool:
    rx = profile.placeholder_regex()
    if not rx:
        return False
    return bool(rx.match(clave_busqueda(rec.get(campo), profile.campo_por_nombre(campo).tipo)))


def calcular_diferencias(store: DataStore, profile: Profile, campo_busqueda: str,
                         mapped_fields: set[str], rows: list[dict]) -> dict:
    """Compara `rows` (ya leídas del Excel, sin normalizar) contra
    `store.records`, buscando por `campo_busqueda`. Solo se comparan los
    campos de `mapped_fields`. Devuelve un dict con:

    - diffs: registros con al menos un dato distinto. Cada uno trae `id`
      (PK, siempre única), `busqueda` (valor de la clave), `old`, `new`,
      `errores` y `redondeos`.
    - conflictos: claves repetidas en el Excel o en el catálogo. No se
      importan. Cada uno trae `codigo` y `motivo`.
    - sin_coincidencia: claves del Excel que no están en el catálogo. Solo aviso.
    - obsoletos: registros del catálogo (no placeholders) que no aparecen en
      el Excel. Cada uno trae `id` y `busqueda`.
    - sin_cambios: cantidad de registros emparejados que ya coinciden.
    - filas_sin_clave: filas del Excel sin valor en la clave de búsqueda.
    """
    campo = profile.campo_por_nombre(campo_busqueda)
    params = [c for c in profile.parametros_visibles() if c.nombre_interno in mapped_fields]
    indice = indice_por_busqueda(store, profile, campo_busqueda)

    filas_por_clave: dict[str, list[dict]] = {}
    filas_sin_clave = 0
    for raw in rows:
        clave = clave_busqueda(raw.get(campo_busqueda), campo.tipo)
        if not clave:
            filas_sin_clave += 1
            continue
        filas_por_clave.setdefault(clave, []).append(raw)

    diffs: list[dict] = []
    conflictos: list[dict] = []
    sin_coincidencia: list[dict] = []
    sin_cambios = 0
    emparejados: set[int] = set()

    for clave in sorted(filas_por_clave, key=str.upper):
        filas = filas_por_clave[clave]
        idxs = indice.get(clave, [])
        emparejados.update(idxs)

        if len(filas) > 1:
            conflictos.append({"codigo": clave,
                               "motivo": f"aparece {len(filas)} veces en el archivo"})
            continue
        if not idxs:
            sin_coincidencia.append({"codigo": clave})
            continue
        if len(idxs) > 1:
            conflictos.append({"codigo": clave,
                               "motivo": f"{len(idxs)} registros del sistema tienen este código"})
            continue

        idx = idxs[0]
        rec = store.records[idx]
        raw = filas[0]
        old_vals, new_vals, differs = {}, {}, False
        for c in params:
            nv = excel_import.normalize_value(raw.get(c.nombre_interno), c.tipo)
            old_vals[c.nombre_interno] = rec[c.nombre_interno]
            new_vals[c.nombre_interno] = nv
            if nv is not None and nv != rec[c.nombre_interno]:
                differs = True
        if not differs:
            sin_cambios += 1
            continue

        # Los valores fuera de rango del perfil (min/max) se detectan acá:
        # un typo en el Excel no debe entrar sin control.
        errores = validacion.validar_valores_de_registro(profile, new_vals)
        redondeos = [c.nombre_interno for c in params
                     if c.tipo in CAMPOS_ENTEROS
                     and excel_import.tuvo_decimales(raw.get(c.nombre_interno))]
        diffs.append({"idx": idx, "id": store.key_of(rec), "busqueda": clave,
                      "old": old_vals, "new": new_vals, "errores": errores,
                      "redondeos": redondeos})

    obsoletos = []
    for i, rec in enumerate(store.records):
        if i in emparejados or _es_placeholder(profile, rec, campo_busqueda):
            continue
        obsoletos.append({"idx": i, "id": store.key_of(rec),
                          "busqueda": clave_busqueda(rec.get(campo_busqueda), campo.tipo)})
    obsoletos.sort(key=lambda d: d["busqueda"].upper())

    return {
        "diffs": diffs,
        "conflictos": conflictos,
        "sin_coincidencia": sin_coincidencia,
        "obsoletos": obsoletos,
        "sin_cambios": sin_cambios,
        "filas_sin_clave": filas_sin_clave,
    }
