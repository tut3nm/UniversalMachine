"""test_app_instancia.py — instancia única por máquina (Nivel 4.4),
integrada con la App real.
============================================================================
Verifica que abrir la misma máquina dos veces en la misma PC (dos ventanas
de App sobre el mismo data_dir) bloquea la segunda con un mensaje claro, y
que cerrar la primera correctamente (_on_close, el camino real de cerrar la
ventana) libera el lock para que una tercera apertura funcione."""

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
import instancia  # noqa: E402


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

    return profile_mod.Profile.load(str(perfil_path)), str(datos_dir)


def test_segunda_ventana_bloqueada_y_liberacion_al_cerrar(tmp_path, monkeypatch, request):
    if not en_subproceso_aislado():
        ejecutar_test_en_subproceso_aislado(request.node.nodeid)
        return

    import app as app_mod

    contenido = "Codigo,Color\r\nA1,1\r\n"
    prof, data_dir = _preparar_maquina(tmp_path, monkeypatch, "lock1", contenido)
    monkeypatch.setattr(app_mod, "error", lambda *a, **k: None)

    ventana1 = app_mod.App([prof])
    try:
        assert hasattr(ventana1, "store")
        assert instancia.leer_lock(data_dir)["pid"] == os.getpid()

        # -- Segunda "instancia" (misma PC, mismo proceso de test) sobre la
        # misma máquina: debe quedar bloqueada, sin store, y autodestruirse
        # (es la primera activación de esa ventana nueva).
        ventana2 = app_mod.App([prof])
        try:
            assert not hasattr(ventana2, "store"), \
                "una segunda ventana sobre la misma máquina no debe poder activarla"
        finally:
            try:
                ventana2.destroy()
            except tk.TclError:
                pass  # ya se autodestruyó al bloquearse: comportamiento esperado

        # El lock sigue siendo el de la primera ventana (no lo pisó la segunda).
        assert instancia.leer_lock(data_dir)["pid"] == os.getpid()
    finally:
        ventana1._on_close()  # camino real de cierre: debe liberar el lock

    assert instancia.leer_lock(data_dir) is None, \
        "cerrar la ventana con _on_close() debe liberar el lock"

    # -- Una tercera apertura, después de liberado, debe funcionar normal --
    ventana3 = app_mod.App([prof])
    try:
        assert hasattr(ventana3, "store")
        assert len(ventana3.store.records) == 1
    finally:
        ventana3._on_close()
