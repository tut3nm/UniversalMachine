"""Sesión de importación desde Excel/CSV (B6 de PLAN_PARIDAD_UI.md) —
equivalente de `ImportDialog` del escritorio:
hoja -> mapeo de columnas -> revisión de diferencias -> aplicar.

Mismo patrón que `wizard_service.py`: estado en memoria del proceso, keyed
por `import_id` (uuid4), con un TTL corto (9.2 del plan: 30 minutos, una
importación a medio revisar no debería quedar viva todo el día si el
operario se va a almorzar)."""

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


def _datos_hoja(s: dict[str, Any], hoja: str) -> dict[str, Any]:
    profile = s["profile"]
    headers = excel_import.read_headers(s["workbook"], hoja)
    guess = excel_import.guess_mapping_generic(headers, profile.campos_visibles())
    # El mapeo recordado de la última importación tiene prioridad sobre la
    # sugerencia automática (app.py:1642): si el operario ya lo confirmó
    # una vez para esta máquina, es más confiable que adivinar por texto.
    mapeo_guardado = import_mapeos.cargar(s["data_dir"])
    guess.update(import_mapeos.aplicar_a_headers(mapeo_guardado, headers))
    sugerencia = {campo: (headers[idx] if idx is not None else None)
                 for campo, idx in guess.items()}

    hoja_obj = s["workbook"][hoja]
    preview = [
        ["" if v is None else v for v in fila[:len(headers)]]
        for fila in hoja_obj.iter_rows(min_row=2, max_row=4, values_only=True)
    ]
    s["hoja"] = hoja
    s["headers"] = headers
    return {"hoja": hoja, "headers": headers, "sugerencia": sugerencia, "preview": preview}


def iniciar(machine_id: str, nombre_archivo: str, contenido: bytes) -> dict[str, Any]:
    _purgar_viejas()
    if not _extension_soportada(nombre_archivo):
        raise ImportacionError(
            "Formato no soportado: subí un archivo .csv, .xlsx o .xlsm.")
    profile = maq_svc.cargar_perfil(machine_id)
    path_actual, _, _ = maq_svc._rutas(profile)  # noqa: SLF001 (mismo módulo lógico)

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


def mapear(import_id: str, mapeo: dict[str, str]) -> dict[str, Any]:
    """Confirma el mapeo columna->campo y calcula las diferencias contra el
    catálogo. Mismas reglas que `ImportDialog._on_mapping` (app.py:1697):
    la clave es obligatoria, hace falta al menos un dato más, y ninguna
    columna puede repetirse entre dos campos."""
    s = _sesion(import_id)
    profile = s["profile"]
    headers = s["headers"]
    clave_nombre = profile.campo_clave().nombre_interno

    mapeo = {k: v for k, v in mapeo.items() if v}
    if clave_nombre not in mapeo:
        raise ImportacionError(
            f"Elegí qué columna del archivo es «{profile.campo_clave().titulo_ui}» "
            "— es obligatoria para poder comparar los registros.")
    if len(mapeo) == 1:
        raise ImportacionError(
            "Además del código, mapeá al menos un dato para poder detectar cambios.")
    if len(set(mapeo.values())) != len(mapeo):
        raise ImportacionError("Cada dato debe ir a una columna distinta.")
    for campo, header in mapeo.items():
        if header not in headers:
            raise ImportacionError(f"La columna '{header}' no existe en la hoja elegida.")

    try:
        import_mapeos.guardar(s["data_dir"], mapeo)
    except OSError:
        pass  # recordar el mapeo es una comodidad, no debe bloquear la importación

    col_by_field = {campo: headers.index(header) for campo, header in mapeo.items()}
    rows = excel_import.read_rows_generic(s["workbook"], s["hoja"], col_by_field)

    store = maq_svc._cargar_store_cacheado(profile)  # noqa: SLF001 — solo lectura para el diff
    mapped_fields = set(mapeo.keys())
    diffs, new_records, obsolete, sin_cambios = importacion.calcular_diferencias(
        store, profile, mapped_fields, rows)

    s["mapped_fields"] = mapped_fields
    s["diffs"] = diffs
    s["new_records"] = new_records
    s["obsolete"] = obsolete

    return {
        "diffs": [{**{k: v for k, v in d.items() if k not in ("errores",)},
                  "errores": _errores_json(d["errores"])} for d in diffs],
        "nuevos": [{**{k: v for k, v in d.items() if k not in ("errores",)},
                   "errores": _errores_json(d["errores"])} for d in new_records],
        "obsoletos": obsolete,
        "sin_cambios": sin_cambios,
    }


def aplicar(import_id: str, diffs_sel: list[str], nuevos_sel: list[str],
           obsoletos_sel: list[str], hash_esperado: str | None) -> dict[str, Any]:
    """Aplica lo que el operario marcó en el paso de revisión. Mismo orden
    que `ImportDialog._on_apply` (app.py:1929): ediciones en el lugar,
    después altas (van al final), y las bajas al final y en orden
    descendente de índice — así ninguna de las dos primeras etapas ve
    corridos los índices que calculó el paso de mapeo."""
    s = _sesion(import_id)
    profile = s["profile"]
    diffs_by_code = {d["code"]: d for d in s.get("diffs", [])}
    new_by_code = {d["code"]: d for d in s.get("new_records", [])}

    store = maq_svc._cargar_store(profile)  # fresca: esta operación muta
    cambios: list[maq_svc.CambioRegistro] = []

    for code in diffs_sel:
        d = diffs_by_code.get(code)
        if d is None or d["errores"]:
            continue
        idx = store.find_key(code)
        if idx == -1:
            continue  # el registro pudo borrarse entre el mapeo y aplicar
        antes = dict(store.records[idx])
        valores = {campo: v for campo, v in d["new"].items() if v is not None}
        store.update(idx, valores)
        cambios.append(maq_svc.CambioRegistro("edicion", code, antes, dict(store.records[idx])))

    for code in nuevos_sel:
        d = new_by_code.get(code)
        if d is None or d["errores"]:
            continue
        if store.find_key(code) != -1:
            continue  # ya lo agregó otra pestaña/importación entre medio
        nuevo = store.nuevo_registro(d["valores"])
        store.add(nuevo)
        cambios.append(maq_svc.CambioRegistro("alta", code, None, nuevo))

    indices_a_borrar = sorted(
        (store.find_key(code) for code in obsoletos_sel), reverse=True)
    for idx in indices_a_borrar:
        if idx == -1:
            continue
        antes = dict(store.records[idx])
        store.delete(idx)
        cambios.append(maq_svc.CambioRegistro("baja", store.key_of(antes), antes, None))

    if not cambios:
        raise ImportacionError("No se seleccionó ningún cambio para aplicar.")

    descripcion = f"Importar cambios ({len(cambios)})"
    nuevo_hash = maq_svc._guardar_con_backup(  # noqa: SLF001 — mismo módulo lógico
        profile, store, cambios, hash_esperado, origen="importacion", descripcion=descripcion)

    del _SESIONES[import_id]
    return {
        "hash": nuevo_hash,
        "modificados": sum(1 for c in cambios if c.accion == "edicion"),
        "nuevos": sum(1 for c in cambios if c.accion == "alta"),
        "eliminados": sum(1 for c in cambios if c.accion == "baja"),
    }
