"""
test_app_historial.py — integración del historial con la App real (Nivel 2.2).
============================================================================
Los tres escenarios comparten UNA sola instancia de App (tb.Window),
cambiando de "máquina" con _activate_profile() en vez de crear una segunda
ventana: ttkbootstrap mantiene un Style singleton por proceso, así que
instanciar más de un tb.Window completo en la misma sesión de pytest rompe
la creación de widgets nuevos (Combobox, etc.) en la segunda/tercera
ventana con un TclError "application has been destroyed" — no es un
problema del código de la app, es una limitación conocida de ttkbootstrap
con múltiples raíces Tk en un mismo proceso.
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
import historial as historial_mod  # noqa: E402


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
    """Idempotente respecto a app_base_dir: todas las máquinas de este test
    comparten la misma tmp_path/app_base_dir (una sola carpeta profiles/ y
    datos/ para el proceso de test), cambia solo el machine_id."""
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


def test_historial_alta_edicion_baja_restauracion_y_visor(tmp_path, monkeypatch, request):
    if not en_subproceso_aislado():
        ejecutar_test_en_subproceso_aislado(request.node.nodeid)
        return

    import app as app_mod

    contenido = "Codigo,Color\r\nA1,1\r\n"
    prof1 = _preparar_maquina(tmp_path, monkeypatch, "hist1", contenido)
    ventana = app_mod.App([prof1])
    try:
        # -- Escenario 1: alta + modificación + baja quedan en el historial --
        assert historial_mod.leer_eventos(ventana.path_historial) == []

        nuevo = ventana.store.nuevo_registro({"code": "A2", "color": 3})
        ventana.store.add(nuevo)
        assert ventana._autosave() is True
        ventana._registrar_evento("alta", "A2", nuevos=nuevo)

        idx = ventana.store.find_key("A1")
        anterior = dict(ventana.store.records[idx])
        ventana.store.update(idx, {"color": 7})
        assert ventana._autosave() is True
        ventana._registrar_evento("modificacion", "A1", anteriores=anterior,
                                  nuevos=dict(ventana.store.records[idx]))

        idx2 = ventana.store.find_key("A2")
        registro_baja = dict(ventana.store.records[idx2])
        ventana.store.delete(idx2)
        assert ventana._autosave() is True
        ventana._registrar_evento("baja", "A2", anteriores=registro_baja)

        eventos = historial_mod.leer_eventos(ventana.path_historial)
        assert [e["accion"] for e in eventos] == ["alta", "modificacion", "baja"]
        assert eventos[0]["clave"] == "A2"
        assert eventos[0]["nuevos"]["color"] == 3
        assert eventos[1]["clave"] == "A1"
        assert eventos[1]["anteriores"]["color"] == 1
        assert eventos[1]["nuevos"]["color"] == 7
        assert eventos[2]["clave"] == "A2"
        assert eventos[2]["anteriores"]["color"] == 3
        assert all(e["usuario"] for e in eventos)
        assert all(e["origen"] == "manual" for e in eventos)

        # -- Escenario 2: restaurar original registra un evento de restauración --
        prof2 = _preparar_maquina(tmp_path, monkeypatch, "hist2", contenido)
        monkeypatch.setattr(app_mod, "confirm", lambda *a, **k: True)
        ventana._activate_profile(prof2)  # misma ventana, otra "máquina"

        ventana.store.update(0, {"color": 9})
        ventana._autosave()
        ventana.on_restore()

        eventos2 = historial_mod.leer_eventos(ventana.path_historial)
        assert eventos2[-1]["accion"] == "restauracion"
        assert eventos2[-1]["origen"] == "restaurar_original"

        # -- Escenario 3: el visor de historial filtra sin crashear --------------
        contenido3 = "Codigo,Color\r\nA1,1\r\nA2,2\r\n"
        prof3 = _preparar_maquina(tmp_path, monkeypatch, "hist3", contenido3)
        ventana._activate_profile(prof3)

        ventana._registrar_evento("alta", "A3", nuevos={"code": "A3", "color": 5})
        ventana._registrar_evento("baja", "A1", anteriores={"code": "A1", "color": 1})

        monkeypatch.setattr(app_mod.HistorialDialog, "wait_visibility", lambda self: None)
        monkeypatch.setattr(app_mod.HistorialDialog, "grab_set", lambda self: None)
        monkeypatch.setattr(app_mod.HistorialDialog, "wait_window", lambda self, w=None: None)

        dlg = app_mod.HistorialDialog(ventana, ventana.path_historial, ventana.data_dir,
                                      ventana.path_actual, ventana.profile, ventana.store)
        try:
            assert len(dlg._todos) == 2
            dlg._filtro_accion.set("Alta")
            dlg._refrescar()
            assert len(dlg._eventos_mostrados) == 1
            assert dlg._eventos_mostrados[0]["clave"] == "A3"

            dlg._filtro_accion.set("Todas")
            dlg._filtro_codigo.set("a1")
            dlg._refrescar()
            assert len(dlg._eventos_mostrados) == 1
            assert dlg._eventos_mostrados[0]["clave"] == "A1"
        finally:
            dlg.destroy()
    finally:
        ventana.destroy()
