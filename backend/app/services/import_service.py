"""Sesión de importación desde Excel/CSV (B6 de PLAN_PARIDAD_UI.md):
hoja -> clave de búsqueda + datos a actualizar -> revisión de diferencias ->
aplicar. Plan: PLAN_IMPORTACION_CLAVE_BUSQUEDA.md.

Mismo patrón que `wizard_service.py`: estado en memoria del proceso, keyed
por `import_id` (uuid4), con un TTL corto (30 minutos)."""

from __future__ import annotations

import dataclasses
import os
import tempfile
import time
import uuid
from typing import Any

from app import _bootstrap  # noqa: F401

import excel_import
import import_mapeos
import importacion
import paths
import validacion

from app.services import maquinas_service as maq_svc

_SESIONES: dict[str, dict[str, Any]] = {}
_TTL_SEGUNDOS = 30 * 60


class ImportacionError(Exception):
    pass


def _purgar_viejas() -> None:
    ahora = time.time()
    vencidas = [iid for iid, s in _SESIONES.items() if ahora - s["creado"] > _TTL_SEGUNDOS]
    for iid in vencidas:
        s = _SESIONES.pop(iid)
        try:
            s["workbook"].close()
        except Exception:
            pass
        try:
            os.remove(s["tmp_path"])
        except OSError:
            pass


def _sesion(import_id: str) -> dict[str, Any]:
    s = _SESIONES.get(import_id)
    if not s:
        raise KeyError(f"Sesión de importación inexistente o vencida: {import_id}")
    return s


def _extension_soportada(nombre_archivo: str) -> bool:
    return nombre_archivo.lower().endswith((".csv", ".xlsx", ".xlsm"))


def _campos_clave_elegibles(profile):
    """Campos que pueden servir de clave de búsqueda: visibles y no sintéticos
    (el ID automático nunca viene en el archivo de la máquina)."""
    return [c for c in profile.campos_visibles() if not c.sintetica]


def _sugerencia_busqueda(profile, headers: list[str], memoria: dict) -> dict[str, str | None]:
    elegibles = _campos_clave_elegibles(profile)
    nombres = {c.nombre_interno for c in elegibles}
    recordada = memoria.get("busqueda")
    if recordada and recordada["campo"] in nombres and recordada["columna"] in headers:
        return {"campo": recordada["campo"], "columna": recordada["columna"]}

    # Sin memoria: la PK si es una clave real (no sintética); si no, nada.
    clave = profile.campo_clave()
    if clave.sintetica:
        return {"campo": None, "columna": None}
    guess = excel_import.guess_mapping_generic(headers, elegibles)
    idx = guess.get(clave.nombre_interno)
    return {"campo": clave.nombre_interno,
            "columna": headers[idx] if idx is not None else None}


def _datos_hoja(s: dict[str, Any], hoja: str) -> dict[str, Any]:
    profile = s["profile"]
    headers = excel_import.read_headers(s["workbook"], hoja)
    memoria = import_mapeos.cargar(s["data_dir"])

    # Sección 2: datos a actualizar (solo parámetros visibles). El mapeo
    # recordado de la última importación tiene prioridad sobre la
    # sugerencia automática por texto.
    parametros = profile.parametros_visibles()
    nombres_param = {c.nombre_interno for c in parametros}
    guess = excel_import.guess_mapping_generic(headers, parametros)
    recordados = {campo: idx for campo, idx in
                  import_mapeos.aplicar_a_headers(memoria["mapeo"], headers).items()
                  if campo in nombres_param}
    guess.update(recordados)
    sugerencia = {campo: (headers[idx] if idx is not None else None)
                  for campo, idx in guess.items()}

    # Sección 1: clave de búsqueda.
    sugerencia_busqueda = _sugerencia_busqueda(profile, headers, memoria)

    hoja_obj = s["workbook"][hoja]
    preview = [
        ["" if v is None else v for v in fila[:len(headers)]]
        for fila in hoja_obj.iter_rows(min_row=2, max_row=4, values_only=True)
    ]
    s["hoja"] = hoja
    s["headers"] = headers
    return {"hoja": hoja, "headers": headers, "sugerencia": sugerencia,
            "sugerencia_busqueda": sugerencia_busqueda, "preview": preview}


def iniciar(machine_id: str, nombre_archivo: str, contenido: bytes) -> dict[str, Any]:
    _purgar_viejas()
    if not _extension_soportada(nombre_archivo):
        raise ImportacionError(
            "Formato no soportado: subí un archivo .csv, .xlsx o .xlsm.")
    profile = maq_svc.cargar_perfil(machine_id)

    fd, tmp_path = tempfile.mkstemp(suffix=os.path.splitext(nombre_archivo)[1] or ".csv")
    with os.fdopen(fd, "wb") as f:
        f.write(contenido)

    try:
        workbook = excel_import.abrir_archivo_importacion(tmp_path)
    except Exception as e:
        os.remove(tmp_path)
        raise ImportacionError(str(e)) from e

    hojas = excel_import.sheet_names(workbook)
    import_id = str(uuid.uuid4())
    _SESIONES[import_id] = {
        "creado": time.time(), "tmp_path": tmp_path, "workbook": workbook,
        "hojas": hojas, "machine_id": machine_id, "profile": profile,
        "data_dir": paths.data_dir_for(profile.id),
    }
    resultado = {"import_id": import_id, "hojas": hojas}
    resultado.update(_datos_hoja(_SESIONES[import_id], hojas[0]))
    return resultado


def elegir_hoja(import_id: str, hoja: str) -> dict[str, Any]:
    s = _sesion(import_id)
    if hoja not in s["hojas"]:
        raise ImportacionError(f"La hoja '{hoja}' no existe en este archivo.")
    return _datos_hoja(s, hoja)


def _errores_json(errores) -> list[dict[str, Any]]:
    return [dataclasses.asdict(e) for e in errores]


def mapear(import_id: str, busqueda: dict[str, str] | None,
           mapeo: dict[str, str]) -> dict[str, Any]:
    """Confirma la clave de búsqueda (sección 1) y el mapeo de datos
    (sección 2), y calcula las diferencias contra el catálogo.

    Reglas: la clave es obligatoria y va a un campo elegible (sin ID); hace
    falta al menos un dato a actualizar; el campo de la clave no se puede
    actualizar; y cada columna del archivo se usa una sola vez."""
    s = _sesion(import_id)
    profile = s["profile"]
    headers = s["headers"]
    elegibles = {c.nombre_interno: c for c in _campos_clave_elegibles(profile)}
    datos = {c.nombre_interno: c for c in profile.parametros_visibles()}

    campo_b = (busqueda or {}).get("campo") or ""
    col_b = (busqueda or {}).get("columna") or ""
    if not campo_b or not col_b:
        raise ImportacionError(
            "Elegí el campo del sistema y la columna del archivo que forman la "
            "clave de búsqueda.")
    if campo_b not in elegibles:
        raise ImportacionError("El campo elegido como clave de búsqueda no se puede usar para buscar.")
    if col_b not in headers:
        raise ImportacionError(f"La columna '{col_b}' no existe en la hoja elegida.")

    mapeo = {k: v for k, v in mapeo.items() if v}
    if not mapeo:
        raise ImportacionError("Mapeá al menos un dato a actualizar.")
    for campo, header in mapeo.items():
        if campo == campo_b or campo not in datos:
            titulo = elegibles.get(campo) or datos.get(campo)
            nombre = titulo.titulo_ui if titulo else campo
            raise ImportacionError(f"«{nombre}» no se puede actualizar desde el archivo.")
        if header not in headers:
            raise ImportacionError(f"La columna '{header}' no existe en la hoja elegida.")
    columnas = [col_b, *mapeo.values()]
    if len(set(columnas)) != len(columnas):
        raise ImportacionError("Cada columna del archivo se usa una sola vez: en la clave o en un dato.")

    try:
        import_mapeos.guardar(s["data_dir"], {"campo": campo_b, "columna": col_b}, mapeo)
    except OSError:
        pass  # recordar el mapeo es una comodidad, no debe bloquear la importación

    col_by_field = {campo_b: headers.index(col_b)}
    col_by_field.update({campo: headers.index(header) for campo, header in mapeo.items()})
    rows = excel_import.read_rows_generic(s["workbook"], s["hoja"], col_by_field)

    store = maq_svc._cargar_store_cacheado(profile)  # noqa: SLF001 — solo lectura para el diff
    r = importacion.calcular_diferencias(store, profile, campo_b, set(mapeo), rows)

    s["modo"] = "actualizacion"
    s["busqueda"] = campo_b
    s["diffs"] = r["diffs"]
    s["obsoletos"] = r["obsoletos"]

    return {
        "diffs": [{**d, "errores": _errores_json(d["errores"])} for d in r["diffs"]],
        "altas": [],
        "conflictos": r["conflictos"],
        "sin_coincidencia": r["sin_coincidencia"],
        "obsoletos": r["obsoletos"],
        "sin_cambios": r["sin_cambios"],
        "filas_sin_clave": r["filas_sin_clave"],
    }


def _valor_carga(raw: object, campo) -> Any:
    """Valor tipado de una celda en la carga masiva: vacía (o no interpretable)
    queda en 0 si el campo es numérico y en None (Null) si es de texto."""
    valor = excel_import.normalize_value(raw, campo.tipo)
    if valor is None or valor == "":
        return 0 if campo.es_numerico else None
    return valor


def mapear_carga(import_id: str, claves: list[dict[str, str]],
                 mapeo: dict[str, str]) -> dict[str, Any]:
    """Carga masiva: cada fila del Excel es un registro. Las claves (1 o 2
    campos) buscan el registro existente; si no hay, la fila se da de alta con
    ID automático; si hay, se modifica con los datos del archivo.

    `claves`: [{"campo": nombre_interno, "columna": encabezado}] (1 o 2).
    `mapeo`: {nombre_interno: encabezado} de los datos que no son clave."""
    s = _sesion(import_id)
    profile = s["profile"]
    headers = s["headers"]
    cargables = {c.nombre_interno: c for c in _campos_clave_elegibles(profile)}
    clave_pk = profile.campo_clave()

    if not 1 <= len(claves) <= 2:
        raise ImportacionError("Elegí una o dos claves de búsqueda.")
    campos_claves = [(k or {}).get("campo") or "" for k in claves]
    columnas_claves = [(k or {}).get("columna") or "" for k in claves]
    if not all(campos_claves) or not all(columnas_claves):
        raise ImportacionError("Cada clave necesita un campo del sistema y una columna del archivo.")
    if len(set(campos_claves)) != len(campos_claves):
        raise ImportacionError("Las dos claves no pueden ser el mismo campo.")
    for campo, col in zip(campos_claves, columnas_claves):
        if campo not in cargables:
            raise ImportacionError("El campo elegido como clave no se puede usar para buscar.")
        if col not in headers:
            raise ImportacionError(f"La columna '{col}' no existe en la hoja elegida.")
    if not clave_pk.sintetica and clave_pk.nombre_interno not in campos_claves:
        raise ImportacionError(
            f"«{clave_pk.titulo_ui}» tiene que ser una de las claves de búsqueda: "
            "es el código que identifica el registro.")

    mapeo = {k: v for k, v in mapeo.items() if v}
    for campo, header in mapeo.items():
        if campo in campos_claves or campo not in cargables:
            titulo = cargables.get(campo)
            nombre = titulo.titulo_ui if titulo else campo
            raise ImportacionError(f"«{nombre}» no se puede cargar desde el archivo.")
        if header not in headers:
            raise ImportacionError(f"La columna '{header}' no existe en la hoja elegida.")
    columnas = [*columnas_claves, *mapeo.values()]
    if len(set(columnas)) != len(columnas):
        raise ImportacionError("Cada columna del archivo se usa una sola vez: en una clave o en un dato.")

    campo_col = {**dict(zip(campos_claves, columnas_claves)), **mapeo}
    col_by_field = {campo: headers.index(col) for campo, col in campo_col.items()}
    rows = excel_import.read_rows_generic(s["workbook"], s["hoja"], col_by_field)

    store = maq_svc._cargar_store_cacheado(profile)  # noqa: SLF001 — solo lectura para el diff
    indice = importacion.indice_por_claves(store, profile, campos_claves)
    pk = clave_pk.nombre_interno

    filas_por_clave: dict[str, list[dict]] = {}
    filas_sin_clave = 0
    for raw in rows:
        partes = [importacion.clave_busqueda(raw.get(c), cargables[c].tipo) for c in campos_claves]
        if not all(partes):
            filas_sin_clave += 1
            continue
        filas_por_clave.setdefault(importacion.clave_compuesta(partes), []).append(raw)

    diffs: list[dict] = []
    altas: list[dict] = []
    conflictos: list[dict] = []
    altas_por_id: dict[str, dict] = {}
    sin_cambios = 0

    for clave in sorted(filas_por_clave, key=str.upper):
        filas = filas_por_clave[clave]
        if len(filas) > 1:
            conflictos.append({"codigo": clave,
                               "motivo": f"aparece {len(filas)} veces en el archivo"})
            continue
        idxs = indice.get(clave, [])
        if len(idxs) > 1:
            conflictos.append({"codigo": clave,
                               "motivo": f"{len(idxs)} registros del sistema tienen esta clave"})
            continue

        raw = filas[0]
        valores = {campo: _valor_carga(raw.get(campo), cargables[campo]) for campo in campo_col}
        errores = validacion.validar_valores_de_registro(profile, valores)

        if not idxs:
            if not profile.id_auto and store.find_key(str(valores[pk])) != -1:
                conflictos.append({"codigo": clave,
                                   "motivo": f"ya existe un registro con el código {valores[pk]}"})
                continue
            altas.append({"id": clave, "busqueda": clave, "new": valores, "errores": errores})
            altas_por_id[clave] = {"valores": valores, "errores": errores}
            continue

        rec = store.records[idxs[0]]
        old = {campo: rec[campo] for campo in valores}
        if all(_sin_vacio(valores[c]) == _sin_vacio(old[c]) for c in valores):
            sin_cambios += 1
            continue
        redondeos = [c for c in campo_col
                     if cargables[c].tipo in CAMPOS_ENTEROS_CARGA
                     and excel_import.tuvo_decimales(raw.get(c))]
        diffs.append({"idx": idxs[0], "id": store.key_of(rec), "busqueda": clave,
                      "old": old, "new": valores, "errores": errores, "redondeos": redondeos})

    s["modo"] = "carga"
    s["claves"] = campos_claves
    s["diffs"] = diffs
    s["obsoletos"] = []
    s["altas"] = altas_por_id

    return {
        "diffs": [{**d, "errores": _errores_json(d["errores"])} for d in diffs],
        "altas": [{**a, "errores": _errores_json(a["errores"])} for a in altas],
        "conflictos": conflictos,
        "sin_coincidencia": [],
        "obsoletos": [],
        "sin_cambios": sin_cambios,
        "filas_sin_clave": filas_sin_clave,
    }


CAMPOS_ENTEROS_CARGA = importacion.CAMPOS_ENTEROS


def _sin_vacio(valor: Any) -> Any:
    """Compara un texto vacío y un Null como iguales (no es un cambio)."""
    return "" if valor is None else valor


def _aplicar_carga(import_id: str, s: dict[str, Any], diffs_sel: list[str],
                   altas_sel: list[str], hash_esperado: str | None) -> dict[str, Any]:
    profile = s["profile"]
    pk = profile.campo_clave().nombre_interno
    diffs_by_id = {d["id"]: d for d in s.get("diffs", [])}
    altas_by_id = s.get("altas", {})

    store = maq_svc._cargar_store(profile)  # fresca: esta operación muta
    indice = importacion.indice_por_claves(store, profile, s["claves"])
    cambios: list[maq_svc.CambioRegistro] = []
    omitidos = 0

    for pk_reg in diffs_sel:
        d = diffs_by_id.get(pk_reg)
        if d is None or d["errores"]:
            continue
        idx = store.find_key(pk_reg)
        if idx == -1 or indice.get(d["busqueda"]) != [idx]:
            omitidos += 1
            continue
        antes = dict(store.records[idx])
        store.update(idx, d["new"])
        cambios.append(maq_svc.CambioRegistro("edicion", pk_reg, antes, dict(store.records[idx])))

    altas_aplicadas = 0
    for clave in altas_sel:
        a = altas_by_id.get(clave)
        if a is None or a["errores"]:
            continue
        if indice.get(clave) or (not profile.id_auto and store.find_key(str(a["valores"][pk])) != -1):
            omitidos += 1
            continue
        nuevo = store.add(store.nuevo_registro(a["valores"]))
        cambios.append(maq_svc.CambioRegistro("alta", store.key_of(nuevo), None, dict(nuevo)))
        altas_aplicadas += 1

    if not cambios:
        raise ImportacionError("No se seleccionó ningún cambio para aplicar.")

    descripcion = f"Carga masiva ({len(cambios)})"
    nuevo_hash = maq_svc._guardar_con_backup(  # noqa: SLF001 — mismo módulo lógico
        profile, store, cambios, hash_esperado, origen="importacion", descripcion=descripcion)

    del _SESIONES[import_id]
    return {
        "hash": nuevo_hash,
        "modificados": sum(1 for c in cambios if c.accion == "edicion"),
        "altas": altas_aplicadas,
        "eliminados": 0,
        "omitidos": omitidos,
    }


def aplicar(import_id: str, diffs_sel: list[str], obsoletos_sel: list[str],
            hash_esperado: str | None, altas_sel: list[str] | None = None) -> dict[str, Any]:
    """Aplica lo que el operario marcó en la revisión. Las modificaciones y las
    bajas se identifican por la PK del registro (`id`), y se vuelven a resolver
    contra el catálogo fresco. En la actualización nunca se crean registros:
    los códigos del Excel que no están en el catálogo solo se avisan. En la
    carga masiva (`altas_sel`) se crean los registros nuevos. El campo de la
    clave de búsqueda y el ID nunca se escriben."""
    s = _sesion(import_id)
    if s.get("modo") == "carga":
        return _aplicar_carga(import_id, s, diffs_sel, altas_sel or [], hash_esperado)
    profile = s["profile"]
    campo_b = s["busqueda"]
    diffs_by_id = {d["id"]: d for d in s.get("diffs", [])}
    obsoletos_ids = {d["id"] for d in s.get("obsoletos", [])}

    store = maq_svc._cargar_store(profile)  # fresca: esta operación muta
    indice = importacion.indice_por_busqueda(store, profile, campo_b)
    cambios: list[maq_svc.CambioRegistro] = []
    omitidos = 0

    for pk in diffs_sel:
        d = diffs_by_id.get(pk)
        if d is None or d["errores"]:
            continue
        idx = store.find_key(pk)
        # Si el registro ya no existe, o su clave dejó de ser única, no se toca.
        if idx == -1 or indice.get(d["busqueda"]) != [idx]:
            omitidos += 1
            continue
        antes = dict(store.records[idx])
        valores = {campo: v for campo, v in d["new"].items() if v is not None}
        store.update(idx, valores)
        cambios.append(maq_svc.CambioRegistro("edicion", pk, antes, dict(store.records[idx])))

    bajas: list[tuple[int, str]] = []
    for pk in obsoletos_sel:
        if pk not in obsoletos_ids:
            continue
        idx = store.find_key(pk)
        if idx == -1:
            omitidos += 1
            continue
        bajas.append((idx, pk))
    # Descendente: borrar un índice no corre los que quedan por borrar.
    for idx, pk in sorted(bajas, reverse=True):
        antes = store.delete(idx)
        cambios.append(maq_svc.CambioRegistro("baja", pk, antes, None))

    if not cambios:
        raise ImportacionError("No se seleccionó ningún cambio para aplicar.")

    descripcion = f"Importar cambios ({len(cambios)})"
    nuevo_hash = maq_svc._guardar_con_backup(  # noqa: SLF001 — mismo módulo lógico
        profile, store, cambios, hash_esperado, origen="importacion", descripcion=descripcion)

    del _SESIONES[import_id]
    return {
        "hash": nuevo_hash,
        "modificados": sum(1 for c in cambios if c.accion == "edicion"),
        "altas": 0,
        "eliminados": sum(1 for c in cambios if c.accion == "baja"),
        "omitidos": omitidos,
    }
