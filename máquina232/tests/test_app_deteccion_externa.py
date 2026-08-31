"""test_app_deteccion_externa.py — detección de modificación externa
(Nivel 4.3), integrada con la App real.
============================================================================
Verifica que _autosave() detecta cuando actual.<ext> cambió por fuera desde
la última carga/guardado, y respeta las tres opciones que el usuario puede
elegir: sobrescribir igual, recargar desde disco (descartando el cambio en
memoria), o cancelar el guardado."""

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


def test_deteccion_externa_sobrescribir_recargar_cancelar(tmp_path, monkeypatch, request):
    """Cubre las tres ramas de _resolver_modificacion_externa() en una app
    real: sobrescribir, recargar desde disco, y cancelar."""
    if not en_subproceso_aislado():
        ejecutar_test_en_subproceso_aislado(request.node.nodeid)
        return

    import app as app_mod

    contenido = "Codigo,Color\r\nA1,1\r\n"
    profile = _preparar_maquina(tmp_path, monkeypatch, "ext1", contenido)
    ventana = app_mod.App([profile])
    monkeypatch.setattr(app_mod, "error", lambda *a, **k: None)
    monkeypatch.setattr(app_mod, "warn", lambda *a, **k: None)

    try:
        # -- Sin modificación externa: no debe preguntar nada --------------
        preguntado = {"veces": 0}

        def _no_deberia_llamarse(*a, **k):
            preguntado["veces"] += 1
            return "Cancelar"

        monkeypatch.setattr(app_mod, "preguntar_opciones", _no_deberia_llamarse)
        ventana.store.update(0, {"color": 5})
        assert ventana._autosave() is True
        assert preguntado["veces"] == 0

        # -- Modificación externa: el usuario elige "Sobrescribir" ---------
        with open(ventana.path_actual, "w", encoding="utf-8", newline="") as f:
            f.write("Codigo,Color\r\nA1,9\r\n")  # cambio "por fuera"
        monkeypatch.setattr(app_mod, "preguntar_opciones",
                            lambda *a, **k: "Sobrescribir con lo mío")
        ventana.store.update(0, {"color": 7})
        assert ventana._autosave() is True
        with open(ventana.path_actual, encoding="utf-8", newline="") as f:
            assert "7" in f.read(), "se sobrescribió con el valor en memoria"

        # -- Modificación externa: el usuario elige "Recargar desde disco" --
        with open(ventana.path_actual, "w", encoding="utf-8", newline="") as f:
            f.write("Codigo,Color\r\nA1,3\r\n")  # cambio "por fuera" otra vez
        monkeypatch.setattr(app_mod, "preguntar_opciones",
                            lambda *a, **k: "Recargar desde disco")
        ventana.store.update(0, {"color": 8})  # este cambio se va a descartar
        assert ventana._autosave() is False
        assert ventana.store.records[0]["color"] == 3, \
            "tras recargar, el store en memoria refleja lo que había en disco"

        # -- Modificación externa: el usuario cancela -----------------------
        with open(ventana.path_actual, "w", encoding="utf-8", newline="") as f:
            f.write("Codigo,Color\r\nA1,4\r\n")
        monkeypatch.setattr(app_mod, "preguntar_opciones", lambda *a, **k: "Cancelar")
        ventana.store.update(0, {"color": 9})
        assert ventana._autosave() is False
        with open(ventana.path_actual, encoding="utf-8", newline="") as f:
            assert "4" in f.read(), "al cancelar, el archivo en disco no se tocó"
        assert ventana.store.records[0]["color"] == 9, \
            "al cancelar, el cambio en memoria del usuario sigue ahí (no se perdió)"
    finally:
        ventana.destroy()
