"""Sesión de wizard de alta/edición de máquina — ver PLAN_WEBAPP.md, Anexo B.

Estado en memoria del proceso, keyed por `wizard_id` (uuid4): la grilla
completa del CSV de muestra se guarda del lado del servidor (no conviene
mandar ida y vuelta un archivo grande con cada request). No sobrevive a un
reinicio del backend ni escala a múltiples workers — aceptable para Fase 1
(un solo operario, un solo proceso, igual que la app Tkinter)."""

from __future__ import annotations

import dataclasses
import os
import tempfile
import time
import uuid
from typing import Any

from app import _bootstrap  # noqa: F401

import paths
import profile_builder as PB
from datastore import DataStore
from profile import Profile, ProfileError

_SESIONES: dict[str, dict[str, Any]] = {}
_TTL_SEGUNDOS = 2 * 60 * 60  # una sesión de wizard abandonada se purga sola


def _purgar_viejas() -> None:
    ahora = time.time()
    vencidas = [wid for wid, s in _SESIONES.items() if ahora - s["creado"] > _TTL_SEGUNDOS]
    for wid in vencidas:
        del _SESIONES[wid]


def _sesion(wizard_id: str) -> dict[str, Any]:
    s = _SESIONES.get(wizard_id)
    if not s:
        raise KeyError(f"Sesión de wizard inexistente o vencida: {wizard_id}")
    return s


class WizardError(Exception):
    pass


def iniciar_alta(nombre_archivo: str, contenido: bytes) -> dict[str, Any]:
    _purgar_viejas()
    tmp_dir = tempfile.mkdtemp(prefix="wizard_")
    csv_path = os.path.join(tmp_dir, nombre_archivo or "muestra.csv")
    with open(csv_path, "wb") as f:
        f.write(contenido)
    info = PB.sniff_csv(csv_path)
    grid = PB.read_grid(csv_path, info["delimitador"])

    wizard_id = str(uuid.uuid4())
    _SESIONES[wizard_id] = {
        "creado": time.time(), "modo": "alta", "csv_path": csv_path,
        "info": info, "grid": grid, "profile_id_existente": None,
    }
    return _resumen_inicio(wizard_id)


def iniciar_edicion(machine_id: str) -> dict[str, Any]:
    _purgar_viejas()
    perfil_path = os.path.join(paths.profiles_dir(), f"maquina_{machine_id}.json")
    if not os.path.exists(perfil_path):
        raise WizardError(f"No existe la máquina '{machine_id}'")
    profile = Profile.load(perfil_path)
    csv_path = os.path.join(paths.data_dir_for(machine_id), f"actual.{profile.extension}")
    if not os.path.exists(csv_path):
        raise WizardError(f"La máquina '{machine_id}' todavía no tiene datos cargados")
    info = PB.sniff_csv(csv_path)
    grid = PB.read_grid(csv_path, info["delimitador"])

    wizard_id = str(uuid.uuid4())
    _SESIONES[wizard_id] = {
        "creado": time.time(), "modo": "edicion", "csv_path": csv_path,
        "info": info, "grid": grid, "profile_id_existente": machine_id,
        "perfil_existente": profile,
    }
    return _resumen_inicio(wizard_id)


def _resumen_inicio(wizard_id: str) -> dict[str, Any]:
    s = _sesion(wizard_id)
    grid = s["grid"]
    return {
        "wizard_id": wizard_id,
        "modo": s["modo"],
        "info": s["info"],
        "n_filas": len(grid),
        "n_columnas": max((len(r) for r in grid), default=0),
        "grid_preview": grid[:12],
    }


def clasificar(wizard_id: str, orientacion: str, primera_col: int = 1) -> dict[str, Any]:
    s = _sesion(wizard_id)
    grid = s["grid"]
    s["orientacion"] = orientacion
    s["primera_col"] = primera_col

    if orientacion == "columnas":
        n_ejes = len(grid)
        clave_sugerida = PB.suggest_clave_row(grid, primera_col)
    else:
        n_ejes = max((len(r) for r in grid), default=0)
        clave_sugerida = 0  # en orientación filas, la 1ra columna suele ser la clave

    filas: list[dict[str, Any]] = []
    for idx in range(n_ejes):
        if orientacion == "columnas":
            row = grid[idx] if idx < len(grid) else []
            etiqueta = (row[0] if row else "").strip()
            muestra = row[primera_col:primera_col + 5]
            kind = PB.classify_row(grid, idx, primera_col)
            if kind == "fija" and clave_sugerida is not None and idx > clave_sugerida:
                kind = "dato"
            valores_para_tipo = row[primera_col:]
        else:
            etiqueta = (grid[0][idx] if grid and idx < len(grid[0]) else "").strip()
            columna = [r[idx] if idx < len(r) else "" for r in grid[1:6]]
            muestra = columna
            kind = "dato"
            valores_para_tipo = [r[idx] if idx < len(r) else "" for r in grid[1:]]

        sugerido = PB.suggest_tipo(valores_para_tipo, s["info"].get("simbolo_decimal"))
        filas.append({
            "idx": idx,
            "etiqueta": etiqueta,
            "muestra": muestra,
            "kind": kind,
            "incluir_default": idx == clave_sugerida or kind == "dato",
            "nombre_default": etiqueta,
            "titulo_default": etiqueta,
            "tipo_sugerido": sugerido["tipo"],
            "formato_sugerido": sugerido["formato"],
        })

    return {"clave_sugerida": clave_sugerida, "filas": filas}


def construir_perfil(wizard_id: str, machine_id: str, nombre: str, descripcion: str,
                      clave_idx: int, filas: list[dict[str, Any]]) -> dict[str, Any]:
    s = _sesion(wizard_id)
    grid = s["grid"]
    orientacion = s["orientacion"]
    primera_col = s.get("primera_col", 1)
    archivo_inicial = os.path.basename(s["csv_path"])

    campos_elegidos = []
    row_kinds: dict[int, str] = {}
    used_names: set[str] = set()
    for f in filas:
        idx = f["idx"]
        if idx == clave_idx:
            continue
        if f.get("incluir"):
            nombre_interno = (f.get("nombre") or "").strip()
            if not nombre_interno:
                raise WizardError(f"Fila/columna {idx}: falta el nombre interno")
            if nombre_interno in used_names:
                raise WizardError(f"Nombre interno repetido: '{nombre_interno}'")
            used_names.add(nombre_interno)
            eje_key = "fila" if orientacion == "columnas" else "columna"
            campo = {
                eje_key: idx,
                "nombre_interno": nombre_interno,
                "titulo_ui": f.get("titulo") or f.get("etiqueta") or nombre_interno,
                "tipo": f.get("tipo", "texto"),
                "formato": f.get("formato") or {},
                "min": f.get("min"), "max": f.get("max"), "default": f.get("default"),
            }
            campos_elegidos.append(campo)
        elif orientacion == "columnas" and f.get("kind_override"):
            row_kinds[idx] = f["kind_override"]

    features = s.get("perfil_existente").features if s.get("perfil_existente") else None
    try:
        if orientacion == "columnas":
            perfil = PB.build_profile_columnas(
                machine_id, nombre, descripcion, archivo_inicial, s["info"],
                grid, primera_col, clave_idx, campos_elegidos, row_kinds,
                features=features,
            )
        else:
            perfil = PB.build_profile_filas(
                machine_id, nombre, descripcion, archivo_inicial, s["info"],
                grid, 0, 1, clave_idx, campos_elegidos,
                features=features,
            )
    except (ValueError, KeyError) as e:
        raise WizardError(str(e)) from e

    s["perfil_dict"] = perfil
    s["machine_id"] = machine_id
    return perfil


def validar(wizard_id: str) -> dict[str, Any]:
    s = _sesion(wizard_id)
    perfil_dict = s.get("perfil_dict")
    if not perfil_dict:
        raise WizardError("Todavía no se armó un perfil en esta sesión (build-profile)")
    try:
        prof = Profile.from_dict(perfil_dict)
        store = DataStore.load(s["csv_path"], prof)
        with open(s["csv_path"], "rb") as f:
            original = f.read()
        regenerado = store.to_text().encode(prof.encoding)
        ok = original == regenerado
        primer_diff = None
        if not ok:
            for i, (a, b) in enumerate(zip(original, regenerado)):
                if a != b:
                    primer_diff = i
                    break
            else:
                primer_diff = min(len(original), len(regenerado))
        resultado = {
            "ok": ok,
            "n_registros": len(store.records),
            "n_visibles": len(prof.campos_visibles()),
            "n_ocultos": len(prof.campos) - len(prof.campos_visibles()),
            "error_msg": None if ok else "El archivo regenerado no es byte-idéntico al original.",
            "primer_diff_byte": primer_diff,
            "orig_len": len(original),
            "regen_len": len(regenerado),
        }
    except (ValueError, ProfileError, OSError, UnicodeDecodeError) as e:
        resultado = {
            "ok": False, "n_registros": 0, "n_visibles": 0, "n_ocultos": 0,
            "error_msg": str(e), "primer_diff_byte": None, "orig_len": None, "regen_len": None,
        }
    s["ultima_validacion_ok"] = resultado["ok"]
    return resultado


def confirmar(wizard_id: str) -> dict[str, Any]:
    s = _sesion(wizard_id)
    if not s.get("ultima_validacion_ok"):
        raise WizardError("No se puede confirmar sin una validación ok=true reciente.")
    perfil_dict = s["perfil_dict"]
    machine_id = s["machine_id"]
    perfil_path = os.path.join(paths.profiles_dir(), f"maquina_{machine_id}.json")

    import io_seguro
    import json as _json

    if s["modo"] == "alta":
        if os.path.exists(perfil_path):
            raise WizardError(f"Ya existe un perfil para '{machine_id}' (condición de carrera)")
        io_seguro.escribir_atomico(perfil_path, _json.dumps(perfil_dict, ensure_ascii=False, indent=2),
                                    encoding="utf-8")
        prof = Profile.from_dict(perfil_dict)
        data_dir = paths.data_dir_for(machine_id)
        actual = os.path.join(data_dir, f"actual.{prof.extension}")
        original = os.path.join(data_dir, f"original.{prof.extension}")
        io_seguro.copiar_atomico(s["csv_path"], original)
        io_seguro.copiar_atomico(s["csv_path"], actual)
    else:
        if os.path.exists(perfil_path):
            ts = time.strftime("%Y%m%d-%H%M%S")
            io_seguro.copiar_atomico(perfil_path, f"{perfil_path}.bak-{ts}")
        io_seguro.escribir_atomico(perfil_path, _json.dumps(perfil_dict, ensure_ascii=False, indent=2),
                                    encoding="utf-8")

    del _SESIONES[wizard_id]
    return {"machine_id": machine_id, "perfil_path": perfil_path}
