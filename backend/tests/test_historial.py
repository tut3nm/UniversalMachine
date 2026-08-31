"""
test_historial.py — Nivel 2.2 del plan de mejoras.
============================================================================
"""

import gzip
import json
import os
import sys
from datetime import datetime, timedelta

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "app", "core"))

import historial  # noqa: E402


def test_registrar_y_leer_un_evento(tmp_path):
    path = tmp_path / "historial.jsonl"
    historial.registrar(str(path), "alta", "A1", anteriores=None,
                        nuevos={"code": "A1", "color": 1}, origen="manual")
    eventos = historial.leer_eventos(str(path))
    assert len(eventos) == 1
    e = eventos[0]
    assert e["accion"] == "alta"
    assert e["clave"] == "A1"
    assert e["nuevos"] == {"code": "A1", "color": 1}
    assert e["origen"] == "manual"
    assert e["usuario"]  # no vacío
    assert "timestamp" in e


def test_registrar_multiples_eventos_conserva_el_orden(tmp_path):
    path = tmp_path / "historial.jsonl"
    historial.registrar(str(path), "alta", "A1")
    historial.registrar(str(path), "modificacion", "A1", anteriores={"color": 1},
                        nuevos={"color": 2})
    historial.registrar(str(path), "baja", "A1")
    eventos = historial.leer_eventos(str(path))
    assert [e["accion"] for e in eventos] == ["alta", "modificacion", "baja"]


def test_accion_invalida_rechazada(tmp_path):
    path = tmp_path / "historial.jsonl"
    with pytest.raises(ValueError):
        historial.registrar(str(path), "accion_inventada", "A1")


def test_leer_eventos_archivo_inexistente_devuelve_vacio(tmp_path):
    path = tmp_path / "no_existe.jsonl"
    assert historial.leer_eventos(str(path)) == []


def test_leer_eventos_ignora_lineas_corruptas(tmp_path):
    path = tmp_path / "historial.jsonl"
    historial.registrar(str(path), "alta", "A1")
    with open(path, "a", encoding="utf-8") as f:
        f.write("esto no es json valido\n")
    historial.registrar(str(path), "baja", "A1")
    eventos = historial.leer_eventos(str(path))
    assert [e["accion"] for e in eventos] == ["alta", "baja"], \
        "la línea corrupta se ignora, no aborta la lectura de las demás"


# -- Rotación por tamaño -------------------------------------------------------

def test_rotar_no_hace_nada_si_es_chico(tmp_path):
    path = tmp_path / "historial.jsonl"
    historial.registrar(str(path), "alta", "A1")
    assert historial.rotar_si_hace_falta(str(path)) is None
    assert os.path.exists(path)


def test_rotar_archiva_y_vacia_cuando_supera_el_tamano(tmp_path, monkeypatch):
    path = tmp_path / "historial.jsonl"
    historial.registrar(str(path), "alta", "A1")
    monkeypatch.setattr(historial, "TAMANO_MAX_BYTES", 1)  # fuerza la rotación

    destino = historial.rotar_si_hace_falta(str(path))
    assert destino is not None
    assert destino.endswith(".gz")
    assert os.path.exists(destino)

    with gzip.open(destino, "rt", encoding="utf-8") as f:
        contenido_archivado = f.read()
    assert '"accion": "alta"' in contenido_archivado

    assert os.path.getsize(path) == 0, "el historial activo queda vacío tras rotar"


# -- Retención por antigüedad (purgar_eventos_viejos) --------------------------

def _escribir_evento_con_fecha(path, fecha: datetime, accion: str, clave: str) -> None:
    evento = {"timestamp": fecha.isoformat(timespec="seconds"), "usuario": "test",
              "accion": accion, "clave": clave, "anteriores": None, "nuevos": None,
              "origen": "manual"}
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(evento, ensure_ascii=False) + "\n")


def test_purgar_no_toca_eventos_recientes(tmp_path):
    path = tmp_path / "historial.jsonl"
    ahora = datetime(2026, 7, 28)
    _escribir_evento_con_fecha(path, ahora - timedelta(days=10), "alta", "A1")
    archivados = historial.purgar_eventos_viejos(str(path), ahora=ahora)
    assert archivados == 0
    assert len(historial.leer_eventos(str(path))) == 1


def test_purgar_archiva_eventos_mas_viejos_que_la_retencion(tmp_path):
    path = tmp_path / "historial.jsonl"
    ahora = datetime(2026, 7, 28)
    _escribir_evento_con_fecha(path, ahora - timedelta(days=400), "alta", "VIEJO")
    _escribir_evento_con_fecha(path, ahora - timedelta(days=5), "alta", "RECIENTE")

    archivados = historial.purgar_eventos_viejos(str(path), ahora=ahora)
    assert archivados == 1

    activos = historial.leer_eventos(str(path))
    assert [e["clave"] for e in activos] == ["RECIENTE"]

    # el evento viejo se archivó comprimido, no se perdió
    archivos_gz = [f for f in os.listdir(tmp_path) if f.endswith(".gz")]
    assert len(archivos_gz) == 1
    with gzip.open(tmp_path / archivos_gz[0], "rt", encoding="utf-8") as f:
        assert "VIEJO" in f.read()


def test_purgar_respeta_retencion_personalizada(tmp_path):
    path = tmp_path / "historial.jsonl"
    ahora = datetime(2026, 7, 28)
    _escribir_evento_con_fecha(path, ahora - timedelta(days=40), "alta", "A1")
    archivados = historial.purgar_eventos_viejos(str(path), dias=30, ahora=ahora)
    assert archivados == 1


def test_purgar_evento_con_timestamp_ilegible_no_se_descarta(tmp_path):
    path = tmp_path / "historial.jsonl"
    with open(path, "w", encoding="utf-8") as f:
        f.write(json.dumps({"timestamp": "no-es-una-fecha", "accion": "alta",
                            "clave": "A1", "usuario": "x", "anteriores": None,
                            "nuevos": None, "origen": "manual"}) + "\n")
    archivados = historial.purgar_eventos_viejos(str(path))
    assert archivados == 0
    assert len(historial.leer_eventos(str(path))) == 1


def test_purgar_sin_historial_no_falla(tmp_path):
    path = tmp_path / "no_existe.jsonl"
    assert historial.purgar_eventos_viejos(str(path)) == 0
