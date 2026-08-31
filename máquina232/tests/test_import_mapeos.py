"""Tests de src/import_mapeos.py (Nivel 4.6: recordar mapeos de columnas)."""

import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "src"))

import import_mapeos  # noqa: E402


def test_cargar_sin_archivo_previo_es_vacio(tmp_path):
    assert import_mapeos.cargar(str(tmp_path)) == {}


def test_guardar_y_cargar_redondea(tmp_path):
    mapeo = {"code": "Codigo", "gramos": "Gramos de Carga"}
    import_mapeos.guardar(str(tmp_path), mapeo)
    assert import_mapeos.cargar(str(tmp_path)) == mapeo


def test_cargar_archivo_corrupto_es_vacio(tmp_path):
    (tmp_path / import_mapeos.NOMBRE_ARCHIVO).write_text("{no es json", encoding="utf-8")
    assert import_mapeos.cargar(str(tmp_path)) == {}


def test_cargar_archivo_con_forma_inesperada_es_vacio(tmp_path):
    (tmp_path / import_mapeos.NOMBRE_ARCHIVO).write_text("[1, 2, 3]", encoding="utf-8")
    assert import_mapeos.cargar(str(tmp_path)) == {}


def test_aplicar_a_headers_traduce_texto_a_indice():
    mapeo = {"code": "Codigo", "gramos": "Gramos"}
    headers = ["Otra", "Codigo", "Gramos"]
    assert import_mapeos.aplicar_a_headers(mapeo, headers) == {"code": 1, "gramos": 2}


def test_aplicar_a_headers_ignora_columnas_que_ya_no_existen():
    mapeo = {"code": "Codigo", "gramos": "Ya no existe"}
    headers = ["Codigo", "Otra"]
    assert import_mapeos.aplicar_a_headers(mapeo, headers) == {"code": 0}
