"""test_app_filtros.py — búsqueda por cualquier campo y filtros de rango
(Nivel 4.7), integrado con la App real."""

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
import filtros  # noqa: E402


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
            {"nombre_interno": "nombre", "rol": "parametro", "columna": 2,
             "etiqueta": "Nombre", "tipo": "texto", "titulo_ui": "Nombre"},
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


def test_busqueda_por_cualquier_campo_y_filtros_de_rango(tmp_path, monkeypatch, request):
    if not en_subproceso_aislado():
        ejecutar_test_en_subproceso_aislado(request.node.nodeid)
        return

    import app as app_mod

    contenido = ("Codigo,Gramos,Nombre\r\n"
                "A1,30,Tapa Azul\r\n"
                "A2,5,Tapa Roja\r\n"
                "B1,35,Base Azul\r\n")
    prof = _preparar_maquina(tmp_path, monkeypatch, "filt1", contenido)
    ventana = app_mod.App([prof])
    monkeypatch.setattr(app_mod, "error", lambda *a, **k: None)

    try:
        # -- Buscar por un campo que NO es el código --------------------------
        ventana.search_var.set("azul")
        ventana.refresh_table()
        visibles = {ventana.store.key_of(r) for _, r in ventana._visible_rows()}
        assert visibles == {"A1", "B1"}

        ventana.search_var.set("")

        # -- Filtro de rango numérico, aplicado directamente vía el dict ------
        ventana._filtros_rango = {"gramos": (20, 40)}
        ventana.refresh_table()
        visibles = {ventana.store.key_of(r) for _, r in ventana._visible_rows()}
        assert visibles == {"A1", "B1"}

        # -- Combinado: búsqueda + rango ---------------------------------------
        ventana.search_var.set("azul")
        visibles = {ventana.store.key_of(r) for _, r in ventana._visible_rows()}
        assert visibles == {"A1", "B1"}
        ventana.search_var.set("roja")
        visibles = {ventana.store.key_of(r) for _, r in ventana._visible_rows()}
        assert visibles == set(), "Tapa Roja tiene 5 gramos, fuera del rango 20-40"

        ventana.search_var.set("")
        ventana._filtros_rango = {}

        # -- FiltrosDialog real: guardar y reaplicar un preset -----------------
        monkeypatch.setattr(app_mod.FiltrosDialog, "wait_visibility", lambda self: None)
        monkeypatch.setattr(app_mod.FiltrosDialog, "grab_set", lambda self: None)
        monkeypatch.setattr(app_mod.FiltrosDialog, "wait_window", lambda self, w=None: None)

        dlg = app_mod.FiltrosDialog(ventana, ventana)
        try:
            var_min, var_max = dlg._entry_vars["gramos"]
            var_min.set("20")
            var_max.set("40")
            monkeypatch.setattr(app_mod.Querybox, "get_string",
                                staticmethod(lambda *a, **k: "Livianos altos"))
            dlg._on_guardar_preset()
        finally:
            dlg.destroy()

        guardados = filtros.cargar_guardados(ventana.data_dir)
        assert len(guardados) == 1
        assert guardados[0]["nombre"] == "Livianos altos"
        assert guardados[0]["rangos"]["gramos"] == [20.0, 40.0]

        # Reabrir el diálogo y aplicar el preset guardado.
        dlg2 = app_mod.FiltrosDialog(ventana, ventana)
        try:
            dlg2._aplicar_preset(guardados[0])
        finally:
            pass  # _aplicar_preset ya llama a self.destroy() vía _on_aplicar()

        assert ventana._filtros_rango["gramos"] == (20.0, 40.0)
        visibles = {ventana.store.key_of(r) for _, r in ventana._visible_rows()}
        assert visibles == {"A1", "B1"}, \
            "A2 tiene 5 gramos, fuera del rango 20-40 del preset aplicado"
    finally:
        ventana._on_close()
