"""Comparación entre el catálogo `actual` y el `original` (Nivel 4.1 del
plan de mejoras). Función pura, sin ninguna dependencia de la UI, para que
se pueda probar sin abrir ninguna ventana y reutilizar tanto para la vista
"Ver cambios" como para el informe exportable."""

from __future__ import annotations

from datastore import DataStore

TIPOS_VALIDOS = {"alta", "baja", "modificacion"}


def comparar_con_original(store_actual: DataStore, store_original: DataStore) -> list[dict]:
    """Compara `store_actual` contra `store_original` (mismo perfil).
    Devuelve una lista de diffs, cada uno con:

    - tipo: "alta" | "baja" | "modificacion"
    - code: la clave del registro
    - anteriores: valores en `original` (None si es alta)
    - nuevos: valores en `actual` (None si es baja)
    - campos_modificados: lista de nombres_internos que cambiaron (solo
      para "modificacion")

    Los placeholders (slots vacíos) no se comparan — no son datos reales.
    Ordenado por código."""
    profile = store_actual.profile
    params = profile.parametros_visibles()

    originales = {store_original.key_of(r): r for r in store_original.records
                 if not store_original.is_placeholder(r)}
    actuales = {store_actual.key_of(r): r for r in store_actual.records
               if not store_actual.is_placeholder(r)}

    diffs: list[dict] = []

    for code, rec in actuales.items():
        if code not in originales:
            diffs.append({"tipo": "alta", "code": code, "anteriores": None,
                          "nuevos": dict(rec), "campos_modificados": []})
            continue
        orig = originales[code]
        campos_modificados = [c.nombre_interno for c in params
                              if rec.get(c.nombre_interno) != orig.get(c.nombre_interno)]
        if campos_modificados:
            diffs.append({"tipo": "modificacion", "code": code,
                          "anteriores": dict(orig), "nuevos": dict(rec),
                          "campos_modificados": campos_modificados})

    for code, rec in originales.items():
        if code not in actuales:
            diffs.append({"tipo": "baja", "code": code, "anteriores": dict(rec),
                          "nuevos": None, "campos_modificados": []})

    diffs.sort(key=lambda d: (d["code"].upper(), d["tipo"]))
    return diffs


def filtrar_por_tipo(diffs: list[dict], tipos: set[str]) -> list[dict]:
    return [d for d in diffs if d["tipo"] in tipos]


def a_filas_csv(profile, diffs: list[dict]) -> list[list[str]]:
    """Convierte los diffs a filas listas para escribir con csv.writer:
    encabezado + una fila por diff, con los valores anteriores/nuevos de
    cada parámetro visible."""
    params = profile.parametros_visibles()
    header = ["tipo", "codigo"] + [f"{c.titulo_ui} (antes)" for c in params] + \
        [f"{c.titulo_ui} (ahora)" for c in params]
    filas = [header]
    for d in diffs:
        ant = d["anteriores"] or {}
        nue = d["nuevos"] or {}
        fila = [d["tipo"], d["code"]]
        fila += [str(ant.get(c.nombre_interno, "")) for c in params]
        fila += [str(nue.get(c.nombre_interno, "")) for c in params]
        filas.append(fila)
    return filas
