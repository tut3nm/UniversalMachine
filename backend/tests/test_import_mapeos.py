"""Tests de src/import_mapeos.py (Nivel 4.6: recordar mapeos de columnas)."""

import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "app", "core"))

import import_mapeos  # noqa: E402

VACIO = {"busqueda": None, "mapeo": {}}


def test_cargar_sin_archivo_previo_es_vacio(tmp_path):
    assert import_mapeos.cargar(str(tmp_path)) == VACIO


def test_guardar_y_cargar_redondea(tmp_path):
    busqueda = {"campo": "code", "columna": "Codigo"}
    mapeo = {"gramos": "Gramos de Carga"}
    import_mapeos.guardar(str(tmp_path), busqueda, mapeo)
    assert import_mapeos.cargar(str(tmp_path)) == {"busqueda": busqueda, "mapeo": mapeo}


def test_formato_anterior_se_lee_como_mapeo_sin_busqueda(tmp_path):
    (tmp_path / import_mapeos.NOMBRE_ARCHIVO).write_text(
        '{"code": "Codigo", "gramos": "Gramos"}', encoding="utf-8")
    assert import_mapeos.cargar(str(tmp_path)) == {
        "busqueda": None, "mapeo": {"code": "Codigo", "gramos": "Gramos"}}


def test_busqueda_incompleta_se_descarta(tmp_path):
    (tmp_path / import_mapeos.NOMBRE_ARCHIVO).write_text(
        '{"busqueda": {"campo": "code"}, "mapeo": {"gramos": "Gramos"}}', encoding="utf-8")
    assert import_mapeos.cargar(str(tmp_path)) == {"busqueda": None, "mapeo": {"gramos": "Gramos"}}


def test_cargar_archivo_corrupto_es_vacio(tmp_path):
    (tmp_path / import_mapeos.NOMBRE_ARCHIVO).write_text("{no es json", encoding="utf-8")
    assert import_mapeos.cargar(str(tmp_path)) == VACIO


def test_cargar_archivo_con_forma_inesperada_es_vacio(tmp_path):
    (tmp_path / import_mapeos.NOMBRE_ARCHIVO).write_text("[1, 2, 3]", encoding="utf-8")
    assert import_mapeos.cargar(str(tmp_path)) == VACIO


def test_aplicar_a_headers_traduce_texto_a_indice():
    mapeo = {"code": "Codigo", "gramos": "Gramos"}
    headers = ["Otra", "Codigo", "Gramos"]
    assert import_mapeos.aplicar_a_headers(mapeo, headers) == {"code": 1, "gramos": 2}


def test_aplicar_a_headers_ignora_columnas_que_ya_no_existen():
    mapeo = {"code": "Codigo", "gramos": "Ya no existe"}
    headers = ["Codigo", "Otra"]
    assert import_mapeos.aplicar_a_headers(mapeo, headers) == {"code": 0}
