"""
test_app_deshacer.py — deshacer/rehacer en sesión (Nivel 2.3).
============================================================================
"""

import json
import os
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "src"))

tk = pytest.importorskip("tkinter")

from conftest import (  # noqa: E402
    tk_disponible, en_subproceso_aislado, ejecutar_test_en_subproceso_aislado,
)

if not tk_disponible():
    pytest.skip("no hay display disponible para Tkinter", allow_module_level=True)

import paths  # noqa: E402
import profile as profile_mod  # noqa: E402


def _perfil_filas_dict(machine_id: str) -> dict:
    return {
        "id": machine_id, "nombre": f"Sintética {machine_id}", "descripcion": "",
        "archivo_inicial": "",
        "archivo": {"extension": "csv", "delimitador": ",", "encoding": "utf-8",
                    "bom": False, "fin_de_linea": "CRLF", "orientacion": "filas"},
        "estructura": {"fila_encabezado": 0, "primera_fila_datos": 1},
        "campos": [
            {"nombre_interno": "code", "rol": "clave", "columna": 0,
             "etiqueta": "Codigo", "tipo": "texto", "titulo_ui": "Código"},
            {"nombre_interno": "color", "rol": "parametro", "columna": 1,
             "etiqueta": "Color", "tipo": "entero", "titulo_ui": "Color",
             "min": 1, "max": 9},
        ],
    }


def _preparar_maquina(tmp_path, monkeypatch, machine_id: str, contenido: str):
    monkeypatch.setattr(paths, "app_base_dir", lambda: str(tmp_path))
    prof_dir = tmp_path / "profiles"
    prof_dir.mkdir(parents=True, exist_ok=True)
    perfil_path = prof_dir / f"maquina_{machine_id}.json"
    perfil_path.write_text(json.dumps(_perfil_filas_dict(machine_id)), encoding="utf-8")

    datos_dir = tmp_path / "datos" / machine_id
    datos_dir.mkdir(parents=True, exist_ok=True)
    with open(datos_dir / "actual.csv", "w", encoding="utf-8", newline="") as f:
        f.write(contenido)
    with open(datos_dir / "original.csv", "w", encoding="utf-8", newline="") as f:
        f.write(contenido)

    return profile_mod.Profile.load(str(perfil_path))


def test_deshacer_y_rehacer_alta_modificacion_y_baja(tmp_path, monkeypatch, request):
    if not en_subproceso_aislado():
        ejecutar_test_en_subproceso_aislado(request.node.nodeid)
        return

    import app as app_mod

    contenido = "Codigo,Color\r\nA1,1\r\n"
    prof = _preparar_maquina(tmp_path, monkeypatch, "undo1", contenido)
    ventana = app_mod.App([prof])
    try:
        assert str(ventana.undo_btn["state"]) == "disabled"
        assert str(ventana.redo_btn["state"]) == "disabled"

        # -- Alta --
        nuevo = ventana.store.nuevo_registro({"code": "A2", "color": 3})
        ventana.store.add(nuevo)
        assert ventana._autosave() is True
        ventana._registrar_cambios("alta de A2",
                                   [app_mod.CambioRegistro("alta", "A2", nuevos=nuevo)])
        assert len(ventana.store.records) == 2
        assert str(ventana.undo_btn["state"]) == "normal"

        ventana.on_deshacer()
        assert ventana.store.find_key("A2") == -1, "el alta se deshizo"
        assert len(ventana.store.records) == 1
        with open(ventana.path_actual, encoding="utf-8", newline="") as f:
            assert f.read() == contenido, "el archivo en disco refleja el deshacer"
        assert str(ventana.redo_btn["state"]) == "normal"

        ventana.on_rehacer()
        assert ventana.store.find_key("A2") != -1, "el alta se rehizo"
        assert len(ventana.store.records) == 2

        # -- Modificación --
        idx = ventana.store.find_key("A1")
        anterior = dict(ventana.store.records[idx])
        ventana.store.update(idx, {"color": 8})
        assert ventana._autosave() is True
        ventana._registrar_cambios(
            "modificación de A1",
            [app_mod.CambioRegistro("modificacion", "A1", anteriores=anterior,
                                    nuevos=dict(ventana.store.records[idx]))])

        ventana.on_deshacer()
        idx = ventana.store.find_key("A1")
        assert ventana.store.records[idx]["color"] == 1, "la modificación se deshizo"

        ventana.on_rehacer()
        idx = ventana.store.find_key("A1")
        assert ventana.store.records[idx]["color"] == 8, "la modificación se rehizo"

        # -- Baja --
        idx2 = ventana.store.find_key("A2")
        registro_baja = dict(ventana.store.records[idx2])
        ventana.store.delete(idx2)
        assert ventana._autosave() is True
        ventana._registrar_cambios(
            "baja de A2", [app_mod.CambioRegistro("baja", "A2", anteriores=registro_baja)])
        assert ventana.store.find_key("A2") == -1

        ventana.on_deshacer()
        assert ventana.store.find_key("A2") != -1, "la baja se deshizo (el registro vuelve)"

        # -- Un nuevo cambio después de deshacer debe vaciar la pila de rehacer --
        ventana.on_deshacer()  # deshace la modificación de A1 otra vez
        assert ventana._pila_rehacer, "hay algo para rehacer en este punto"
        nuevo2 = ventana.store.nuevo_registro({"code": "A3", "color": 5})
        ventana.store.add(nuevo2)
        assert ventana._autosave() is True
        ventana._registrar_cambios("alta de A3",
                                   [app_mod.CambioRegistro("alta", "A3", nuevos=nuevo2)])
        assert ventana._pila_rehacer == [], \
            "un cambio nuevo debe descartar cualquier 'rehacer' pendiente"

    finally:
        ventana.destroy()


def test_deshacer_vacio_no_hace_nada(tmp_path, monkeypatch, request):
    if not en_subproceso_aislado():
        ejecutar_test_en_subproceso_aislado(request.node.nodeid)
        return

    import app as app_mod

    contenido = "Codigo,Color\r\nA1,1\r\n"
    prof = _preparar_maquina(tmp_path, monkeypatch, "undo2", contenido)
    ventana = app_mod.App([prof])
    try:
        ventana.on_deshacer()  # no debe lanzar ninguna excepción
        ventana.on_rehacer()
        assert len(ventana.store.records) == 1
    finally:
        ventana.destroy()


def test_restaurar_original_vacia_la_pila_de_deshacer(tmp_path, monkeypatch, request):
    if not en_subproceso_aislado():
        ejecutar_test_en_subproceso_aislado(request.node.nodeid)
        return

    import app as app_mod

    contenido = "Codigo,Color\r\nA1,1\r\n"
    prof = _preparar_maquina(tmp_path, monkeypatch, "undo3", contenido)
    monkeypatch.setattr(app_mod, "confirm", lambda *a, **k: True)

    ventana = app_mod.App([prof])
    try:
        ventana.store.update(0, {"color": 9})
        assert ventana._autosave() is True
        ventana._registrar_cambios(
            "modificación de A1",
            [app_mod.CambioRegistro("modificacion", "A1", anteriores={"code": "A1", "color": 1},
                                    nuevos={"code": "A1", "color": 9})])
        assert ventana._pila_deshacer

        ventana.on_restore()
        assert ventana._pila_deshacer == []
        assert ventana._pila_rehacer == []
        assert str(ventana.undo_btn["state"]) == "disabled"
    finally:
        ventana.destroy()
