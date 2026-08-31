"""
test_app_resiliencia.py — activación de perfil resiliente (Nivel 1.5).
============================================================================
Instancia la App real (Tkinter) con un archivo actual.csv corrupto y
verifica que, en vez de crashear con un traceback, ofrece recuperación y
termina con los datos cargados desde el original. Requiere un entorno con
soporte de Tkinter (se salta automáticamente si no hay display disponible).
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
    """Orientación 'filas' con columnas resueltas por ETIQUETA (sin
    'columna' fija): así, un encabezado que no trae 'Color'/'Peso' hace que
    DataStore.load() levante ValueError de inmediato — el escenario que
    _cargar_datastore_resiliente() tiene que manejar sin crashear."""
    return {
        "id": machine_id, "nombre": f"Sintética {machine_id}", "descripcion": "",
        "archivo_inicial": "",
        "archivo": {"extension": "csv", "delimitador": ",", "encoding": "utf-8",
                    "bom": False, "fin_de_linea": "CRLF", "orientacion": "filas"},
        "estructura": {"fila_encabezado": 0, "primera_fila_datos": 1},
        "campos": [
            {"nombre_interno": "code", "rol": "clave", "etiqueta": "Codigo",
             "tipo": "texto", "titulo_ui": "Código"},
            {"nombre_interno": "color", "rol": "parametro", "etiqueta": "Color",
             "tipo": "entero", "titulo_ui": "Color", "min": 1, "max": 9},
            {"nombre_interno": "peso", "rol": "parametro", "etiqueta": "Peso",
             "tipo": "decimal", "titulo_ui": "Peso",
             "formato": {"separador_decimal": ".", "decimales": 2}},
        ],
    }


def _preparar_maquina(tmp_path, monkeypatch, machine_id: str,
                      contenido_actual: str, contenido_original: str):
    """Redirige toda la app (perfiles + datos) a tmp_path, para no tocar
    nada del repo ni de una instalación real."""
    monkeypatch.setattr(paths, "app_base_dir", lambda: str(tmp_path))

    prof_dir = tmp_path / "profiles"
    prof_dir.mkdir(parents=True, exist_ok=True)
    perfil_path = prof_dir / f"maquina_{machine_id}.json"
    perfil_path.write_text(json.dumps(_perfil_filas_dict(machine_id)), encoding="utf-8")

    datos_dir = tmp_path / "datos" / machine_id
    datos_dir.mkdir(parents=True, exist_ok=True)
    with open(datos_dir / "actual.csv", "w", encoding="utf-8", newline="") as f:
        f.write(contenido_actual)
    with open(datos_dir / "original.csv", "w", encoding="utf-8", newline="") as f:
        f.write(contenido_original)

    return profile_mod.Profile.load(str(perfil_path))


def test_activacion_resiliente_recupera_o_cierra_segun_la_eleccion(tmp_path, monkeypatch, request):
    """Cubre las dos ramas de _activate_profile() ante un actual.csv
    corrupto en un solo test: recuperar vía 'Restaurar el original', y
    cancelar (que debe cerrar la app de forma controlada, sin traceback).

    Se relanza como subproceso aislado (ver conftest.py): instanciar más de
    una App (tb.Window) real en el mismo proceso de pytest —incluso en
    tests o archivos distintos— es frágil por un Style singleton de
    ttkbootstrap atado al proceso."""
    if not en_subproceso_aislado():
        ejecutar_test_en_subproceso_aislado(request.node.nodeid)
        return

    import gc

    import app as app_mod

    contenido_original = "Codigo,Color,Peso\r\nA1,1,10.00\r\n"
    # Encabezado sin 'Color' ni 'Peso': DataStore.load() levanta ValueError
    # ("No encuentro la columna...") apenas se llama, sin llegar a cargar nada.
    contenido_actual_corrupto = "Codigo,OtraColumnaQueNoExiste\r\nA1,999\r\n"

    # -- Escenario 1: el usuario elige "Restaurar el original" -----------------
    prof1 = _preparar_maquina(tmp_path, monkeypatch, "resil1",
                              contenido_actual_corrupto, contenido_original)
    respuestas = iter(["Restaurar el original"])
    monkeypatch.setattr(app_mod, "preguntar_opciones",
                        lambda *a, **k: next(respuestas, "Cancelar"))
    monkeypatch.setattr(app_mod, "error", lambda *a, **k: None)
    monkeypatch.setattr(app_mod, "warn", lambda *a, **k: None)

    ventana1 = app_mod.App([prof1])
    assert hasattr(ventana1, "store"), \
        "tras 'Restaurar el original' la app debe terminar con una máquina activa"
    assert len(ventana1.store.records) == 1
    assert ventana1.store.records[0]["code"] == "A1"
    with open(ventana1.path_actual, encoding="utf-8", newline="") as f:
        assert f.read() == contenido_original, \
            "el archivo actual en disco quedó igual al original (restaurado)"
    ventana1.update()
    ventana1.destroy()
    ventana1.update()
    del ventana1
    gc.collect()

    # -- Escenario 2: el usuario cancela (no hay máquina previa activa) --------
    prof2 = _preparar_maquina(tmp_path, monkeypatch, "resil2",
                              contenido_actual_corrupto, contenido_original)
    monkeypatch.setattr(app_mod, "preguntar_opciones", lambda *a, **k: "Cancelar")

    ventana2 = app_mod.App([prof2])
    try:
        assert not hasattr(ventana2, "store"), \
            "si se cancela sin ninguna máquina previa activa, no debe quedar un store a medias"
    finally:
        try:
            ventana2.destroy()
        except tk.TclError:
            pass  # ya se auto-destruyó al cancelar: es el comportamiento esperado
