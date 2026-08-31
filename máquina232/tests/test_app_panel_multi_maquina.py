"""test_app_panel_multi_maquina.py — panel multi-máquina (Nivel 4.9),
integrado con la App real."""

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


def _perfil_dict(machine_id: str) -> dict:
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


def _preparar_maquina(tmp_path, machine_id: str, contenido: str, prof_dir, datos_root):
    perfil_path = prof_dir / f"maquina_{machine_id}.json"
    perfil_path.write_text(json.dumps(_perfil_dict(machine_id)), encoding="utf-8")
    datos_dir = datos_root / machine_id
    datos_dir.mkdir(parents=True, exist_ok=True)
    with open(datos_dir / "actual.csv", "w", encoding="utf-8", newline="") as f:
        f.write(contenido)
    with open(datos_dir / "original.csv", "w", encoding="utf-8", newline="") as f:
        f.write(contenido)
    return profile_mod.Profile.load(str(perfil_path))


def test_panel_muestra_resumen_de_cada_maquina_y_permite_saltar(tmp_path, monkeypatch, request):
    if not en_subproceso_aislado():
        ejecutar_test_en_subproceso_aislado(request.node.nodeid)
        return

    import app as app_mod

    monkeypatch.setattr(paths, "app_base_dir", lambda: str(tmp_path))
    prof_dir = tmp_path / "profiles"
    prof_dir.mkdir(parents=True, exist_ok=True)
    datos_root = tmp_path / "datos"

    prof1 = _preparar_maquina(tmp_path, "panel1", "Codigo,Gramos\r\nA1,10\r\n",
                              prof_dir, datos_root)
    prof2 = _preparar_maquina(tmp_path, "panel2", "Codigo,Gramos\r\nB1,20\r\nB2,999\r\n",
                              prof_dir, datos_root)  # B2 fuera de rango: 1 alerta
    prof3 = _preparar_maquina(tmp_path, "panel3", "Codigo,Gramos\r\nC1,5\r\n",
                              prof_dir, datos_root)

    monkeypatch.setattr(app_mod.MachineSelector, "wait_visibility", lambda self: None)
    monkeypatch.setattr(app_mod.MachineSelector, "grab_set", lambda self: None)
    monkeypatch.setattr(app_mod.MachineSelector, "wait_window", lambda self, w=None: None)

    ventana = app_mod.App([prof1, prof2, prof3])
    monkeypatch.setattr(app_mod.PanelMultiMaquinaDialog, "wait_visibility", lambda self: None)
    monkeypatch.setattr(app_mod.PanelMultiMaquinaDialog, "grab_set", lambda self: None)
    monkeypatch.setattr(app_mod.PanelMultiMaquinaDialog, "wait_window", lambda self, w=None: None)

    try:
        dlg = app_mod.PanelMultiMaquinaDialog(ventana, ventana)
        try:
            resumenes_por_id = {r.id: r for r in dlg._resumenes}
            assert resumenes_por_id["panel1"].cantidad_registros == 1
            assert resumenes_por_id["panel2"].cantidad_registros == 2
            assert resumenes_por_id["panel2"].alertas_salud == 1
            assert resumenes_por_id["panel3"].cantidad_registros == 1

            # Saltar a "panel3" desde el panel (la ventana estaba en la
            # primera máquina activada por defecto).
            idx_panel3 = next(i for i, r in enumerate(dlg._resumenes) if r.id == "panel3")
            dlg.tree.selection_set(str(idx_panel3))
            dlg._ir_a_maquina()
        finally:
            pass  # _ir_a_maquina ya se destruye a sí mismo

        assert ventana.profile.id == "panel3"
        assert ventana.store.records[0]["code"] == "C1"
    finally:
        ventana._on_close()
