"""
test_app_backups.py — integración de backups con la App real (Nivel 2.1).
============================================================================
Verifica que _autosave() efectivamente crea un backup antes de sobreescribir
actual.<ext>, y que on_backups() recarga el store correctamente después de
una restauración (simulando el diálogo, sin necesidad de clickear widgets).
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
import backups as backups_mod  # noqa: E402


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


def test_autosave_crea_backup_y_on_backups_recarga_tras_restaurar(tmp_path, monkeypatch, request):
    if not en_subproceso_aislado():
        ejecutar_test_en_subproceso_aislado(request.node.nodeid)
        return

    import app as app_mod

    contenido = "Codigo,Color\r\nA1,1\r\nA2,2\r\n"
    prof = _preparar_maquina(tmp_path, monkeypatch, "back1", contenido)

    ventana = app_mod.App([prof])
    try:
        assert backups_mod.listar_backups(ventana.data_dir) == []

        ventana.store.update(0, {"color": 5})
        assert ventana._autosave() is True, "el autoguardado debe reportar éxito"

        listado = backups_mod.listar_backups(ventana.data_dir)
        assert len(listado) == 1, "_autosave() debe crear un backup del estado PREVIO al guardado"
        with open(listado[0].ruta, encoding="utf-8", newline="") as f:
            assert f.read() == contenido, \
                "el backup conserva el contenido de ANTES de la edición"
        assert backups_mod.verificar_integridad(listado[0]) is True

        # Segunda edición: debe crear un SEGUNDO backup (el estado con color=5).
        ventana.store.update(1, {"color": 7})
        assert ventana._autosave() is True
        listado2 = backups_mod.listar_backups(ventana.data_dir)
        assert len(listado2) == 2

        # -- Simular la restauración desde el diálogo (sin abrir la UI real) --
        backup_mas_viejo = sorted(listado2, key=lambda b: b.timestamp)[0]
        backups_mod.restaurar_backup(backup_mas_viejo, ventana.path_actual)

        class _FakeDialog:
            restaurado = True

        monkeypatch.setattr(app_mod, "BackupsDialog", lambda *a, **k: _FakeDialog())
        ventana.on_backups()

        assert ventana.store.records[0]["color"] == 1, \
            "on_backups() debe recargar self.store con el contenido restaurado"
        assert ventana.store.records[1]["color"] == 2
    finally:
        ventana.destroy()
