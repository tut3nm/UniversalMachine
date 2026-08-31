"""test_app_edicion_en_linea.py — edición en línea y edición masiva
(Nivel 4.8), integrado con la App real."""

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
            {"nombre_interno": "gramos", "rol": "parametro", "columna": 1,
             "etiqueta": "Gramos", "tipo": "entero", "titulo_ui": "Gramos",
             "min": 0, "max": 100},
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


def test_edicion_en_linea_valor_valido_e_invalido(tmp_path, monkeypatch, request):
    if not en_subproceso_aislado():
        ejecutar_test_en_subproceso_aislado(request.node.nodeid)
        return

    import app as app_mod

    contenido = "Codigo,Gramos\r\nA1,10\r\nA2,20\r\n"
    prof = _preparar_maquina(tmp_path, monkeypatch, "inline1", contenido)
    ventana = app_mod.App([prof])
    avisos = []
    monkeypatch.setattr(app_mod, "warn", lambda parent, title, msg: avisos.append(msg))

    try:
        campo_gramos = ventana.profile.campo_por_nombre("gramos")

        # -- Aplicar directo (equivalente a confirmar la celda con Enter) ----
        ventana._aplicar_edicion_celda(0, campo_gramos, 55)
        assert ventana.store.records[0]["gramos"] == 55
        with open(ventana.path_actual, encoding="utf-8", newline="") as f:
            assert "55" in f.read()

        # -- Valor fuera de rango: el parseo debe rechazarlo antes de aplicar -
        valor, error = app_mod.validacion.parsear_valor_campo(campo_gramos, "999")
        assert valor is None
        assert error is not None
        assert ventana.store.records[0]["gramos"] == 55, \
            "un valor inválido nunca debe llegar a aplicarse"

        # -- Se registró en el historial como una modificación ---------------
        eventos = app_mod.historial.leer_eventos(ventana.path_historial)
        assert eventos[-1]["accion"] == "modificacion"
        assert eventos[-1]["clave"] == "A1"

        # -- Deshacer revierte la edición en línea como cualquier otra --------
        ventana.on_deshacer()
        assert ventana.store.records[0]["gramos"] == 10
    finally:
        ventana._on_close()


def test_edicion_masiva_aplica_a_todos_los_seleccionados(tmp_path, monkeypatch, request):
    if not en_subproceso_aislado():
        ejecutar_test_en_subproceso_aislado(request.node.nodeid)
        return

    import app as app_mod

    contenido = "Codigo,Gramos\r\nA1,10\r\nA2,20\r\nA3,30\r\n"
    prof = _preparar_maquina(tmp_path, monkeypatch, "bulk1", contenido)
    ventana = app_mod.App([prof])
    monkeypatch.setattr(app_mod, "confirm", lambda *a, **k: True)
    monkeypatch.setattr(app_mod.BulkEditDialog, "wait_visibility", lambda self: None)
    monkeypatch.setattr(app_mod.BulkEditDialog, "grab_set", lambda self: None)
    monkeypatch.setattr(app_mod.BulkEditDialog, "wait_window", lambda self, w=None: None)

    try:
        # -- Menos de dos seleccionados: no debe abrir el diálogo -------------
        ventana.tree.selection_set("0")
        avisos = []
        monkeypatch.setattr(app_mod, "info", lambda parent, title, msg: avisos.append(msg))
        ventana.on_bulk_edit()
        assert avisos, "con un solo registro seleccionado debe avisar, no abrir el diálogo"

        # -- Dos o más seleccionados: aplica el valor a todos ------------------
        ventana.tree.selection_set("0", "1")
        dlg = app_mod.BulkEditDialog(ventana, ventana, [0, 1])
        try:
            dlg._campo_var.set("Gramos")
            dlg._valor_var.set("77")
            dlg._on_aplicar()
        finally:
            pass  # _on_aplicar ya se destruye a sí mismo si tuvo éxito

        assert ventana.store.records[0]["gramos"] == 77
        assert ventana.store.records[1]["gramos"] == 77
        assert ventana.store.records[2]["gramos"] == 30, "el no seleccionado no se toca"

        # Quedó como UN solo comando deshacible.
        ventana.on_deshacer()
        assert ventana.store.records[0]["gramos"] == 10
        assert ventana.store.records[1]["gramos"] == 20
    finally:
        ventana._on_close()
