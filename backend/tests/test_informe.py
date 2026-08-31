"""Tests de src/informe.py (Nivel 4.2: informe de cambios exportable)."""

import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "app", "core"))

from informe import a_filas_csv, ENCABEZADO  # noqa: E402


def test_lista_vacia_devuelve_solo_encabezado():
    assert a_filas_csv([]) == [ENCABEZADO]


def test_evento_modificacion_incluye_valores_como_json():
    eventos = [{
        "timestamp": "2026-07-29T10:00:00", "usuario": "operario1",
        "accion": "modificacion", "clave": "A1", "origen": "manual",
        "version": "0.4.0",
        "anteriores": {"gramos": 10}, "nuevos": {"gramos": 20},
    }]
    filas = a_filas_csv(eventos)
    assert filas[0] == ENCABEZADO
    fila = filas[1]
    assert fila[0] == "2026-07-29T10:00:00"
    assert fila[1] == "operario1"
    assert fila[2] == "Modificación"
    assert fila[3] == "A1"
    assert fila[4] == "manual"
    assert fila[5] == "0.4.0"
    assert '"gramos": 10' in fila[6]
    assert '"gramos": 20' in fila[7]


def test_evento_sin_version_ni_valores_no_rompe():
    eventos = [{"timestamp": "t", "usuario": "u", "accion": "restauracion",
               "clave": "*", "origen": "restaurar_original"}]
    filas = a_filas_csv(eventos)
    fila = filas[1]
    assert fila[2] == "Restauración"
    assert fila[5] == ""
    assert fila[6] == ""
    assert fila[7] == ""


def test_accion_desconocida_se_muestra_tal_cual():
    eventos = [{"timestamp": "t", "usuario": "u", "accion": "algo_nuevo", "clave": "X"}]
    filas = a_filas_csv(eventos)
    assert filas[1][2] == "algo_nuevo"
