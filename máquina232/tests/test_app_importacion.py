"""test_app_importacion.py — importación desde CSV, mapeos recordados y
vista previa (Nivel 4.6), integrado con ImportDialog real."""

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
import excel_import  # noqa: E402
import import_mapeos  # noqa: E402


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


def test_importar_csv_recuerda_mapeo_y_muestra_vista_previa(tmp_path, monkeypatch, request):
    if not en_subproceso_aislado():
        ejecutar_test_en_subproceso_aislado(request.node.nodeid)
        return

    import app as app_mod

    contenido = "Codigo,Gramos\r\nA1,10\r\n"
    prof = _preparar_maquina(tmp_path, monkeypatch, "imp1", contenido)
    ventana = app_mod.App([prof])
    monkeypatch.setattr(app_mod, "error", lambda *a, **k: None)
    monkeypatch.setattr(app_mod, "warn", lambda *a, **k: None)
    monkeypatch.setattr(app_mod.ImportDialog, "wait_visibility", lambda self: None)
    monkeypatch.setattr(app_mod.ImportDialog, "grab_set", lambda self: None)
    monkeypatch.setattr(app_mod.ImportDialog, "wait_window", lambda self, w=None: None)

    try:
        # -- Importar un CSV (sin openpyxl de por medio) --------------------
        csv_path = tmp_path / "excel_export.csv"
        csv_path.write_text("Codigo,Gramos\r\nA1,12,5\r\n".replace(",5", ""),
                            encoding="utf-8-sig", newline="")
        # (arriba se evita meter una coma decimal en un CSV separado por
        # comas — se prueba el redondeo/separador de miles aparte, en
        # test_excel_import.py; acá el foco es CSV + mapeo + preview)
        csv_path.write_text("Codigo,Gramos\r\nA1,12\r\nA2,7\r\n",
                            encoding="utf-8-sig", newline="")

        workbook = excel_import.abrir_archivo_importacion(str(csv_path))
        assert isinstance(workbook, excel_import.WorkbookCSV)

        dlg = app_mod.ImportDialog(ventana, ventana.store, workbook, "excel_export.csv",
                                   ventana.data_dir)
        try:
            assert dlg.sheet == "CSV"
            # El mapeo se adivinó solo (nombres de columna casi idénticos)
            assert dlg._combo_vars["code"].get() == "Codigo"
            assert dlg._combo_vars["gramos"].get() == "Gramos"

            dlg._on_mapping()
            assert len(dlg.diffs) == 1  # A1 cambia de 10 a 12
            assert len(dlg.new_records) == 1  # A2 es nuevo

            # El mapeo confirmado quedó guardado para la máquina.
            guardado = import_mapeos.cargar(ventana.data_dir)
            assert guardado == {"code": "Codigo", "gramos": "Gramos"}
        finally:
            dlg.destroy()
        workbook.close()

        # -- Una segunda importación, con guess_mapping_generic desactivado
        # (para probar que el mapeo GUARDADO por sí solo es suficiente) ----
        monkeypatch.setattr(excel_import, "guess_mapping_generic",
                            lambda headers, campos: {})
        workbook2 = excel_import.abrir_archivo_importacion(str(csv_path))
        dlg2 = app_mod.ImportDialog(ventana, ventana.store, workbook2, "excel_export.csv",
                                    ventana.data_dir)
        try:
            assert dlg2._combo_vars["code"].get() == "Codigo", \
                "el mapeo guardado debe preseleccionar el combo aunque la sugerencia falle"
            assert dlg2._combo_vars["gramos"].get() == "Gramos"
        finally:
            dlg2.destroy()
        workbook2.close()
    finally:
        ventana._on_close()
