"""Tests de src/importacion.py (calcular_diferencias), extraído de
ImportDialog._compute_diffs en el Nivel 3.1 del plan de mejoras."""

import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "app", "core"))

from profile import Profile  # noqa: E402
from datastore import DataStore  # noqa: E402
from importacion import calcular_diferencias  # noqa: E402


def _perfil():
    campos = [
        {"nombre_interno": "code", "rol": "clave", "columna": 0,
         "etiqueta": "Codigo", "tipo": "texto", "titulo_ui": "Código"},
        {"nombre_interno": "gramos", "rol": "parametro", "columna": 1,
         "etiqueta": "Gramos", "tipo": "entero", "titulo_ui": "Gramos",
         "min": 0, "max": 100, "default": 0},
        {"nombre_interno": "nombre", "rol": "parametro", "columna": 2,
         "etiqueta": "Nombre", "tipo": "texto", "titulo_ui": "Nombre"},
    ]
    estructura = {"fila_encabezado": 0, "primera_fila_datos": 1}
    data = {
        "id": "synth-filas", "nombre": "Sintético filas", "descripcion": "",
        "archivo_inicial": "",
        "archivo": {"extension": "csv", "delimitador": ",",
                    "encoding": "utf-8", "bom": False,
                    "fin_de_linea": "LF", "orientacion": "filas"},
        "estructura": estructura,
        "campos": campos,
        "features": {},
    }
    return Profile.from_dict(data)


def _store(records):
    profile = _perfil()
    return profile, DataStore(profile, records)


def test_registro_modificado_se_detecta_como_diff():
    profile, store = _store([{"code": "A1", "gramos": 10, "nombre": "Uno"}])
    rows = [{"code": "A1", "gramos": "20", "nombre": "Uno"}]
    diffs, new_records, obsolete, unchanged = calcular_diferencias(
        store, profile, {"code", "gramos", "nombre"}, rows)
    assert len(diffs) == 1
    assert diffs[0]["code"] == "A1"
    assert diffs[0]["new"]["gramos"] == 20
    assert diffs[0]["old"]["gramos"] == 10
    assert not diffs[0]["errores"]
    assert new_records == []
    assert obsolete == []
    assert unchanged == 0


def test_registro_sin_cambios_cuenta_como_unchanged():
    profile, store = _store([{"code": "A1", "gramos": 10, "nombre": "Uno"}])
    rows = [{"code": "A1", "gramos": "10", "nombre": "Uno"}]
    diffs, new_records, obsolete, unchanged = calcular_diferencias(
        store, profile, {"code", "gramos", "nombre"}, rows)
    assert diffs == []
    assert unchanged == 1


def test_codigo_nuevo_se_detecta_como_new_record():
    profile, store = _store([{"code": "A1", "gramos": 10, "nombre": "Uno"}])
    rows = [{"code": "A1", "gramos": "10", "nombre": "Uno"},
            {"code": "B2", "gramos": "5", "nombre": "Dos"}]
    diffs, new_records, obsolete, unchanged = calcular_diferencias(
        store, profile, {"code", "gramos", "nombre"}, rows)
    assert len(new_records) == 1
    assert new_records[0]["code"] == "B2"
    assert new_records[0]["valores"]["gramos"] == 5


def test_codigo_ausente_del_excel_se_detecta_como_obsoleto():
    profile, store = _store([{"code": "A1", "gramos": 10, "nombre": "Uno"},
                              {"code": "B2", "gramos": 5, "nombre": "Dos"}])
    rows = [{"code": "A1", "gramos": "10", "nombre": "Uno"}]
    diffs, new_records, obsolete, unchanged = calcular_diferencias(
        store, profile, {"code", "gramos", "nombre"}, rows)
    assert len(obsolete) == 1
    assert obsolete[0]["code"] == "B2"


def test_valor_fuera_de_rango_se_marca_con_errores():
    profile, store = _store([{"code": "A1", "gramos": 10, "nombre": "Uno"}])
    rows = [{"code": "A1", "gramos": "999", "nombre": "Uno"}]
    diffs, new_records, obsolete, unchanged = calcular_diferencias(
        store, profile, {"code", "gramos", "nombre"}, rows)
    assert len(diffs) == 1
    assert diffs[0]["errores"]


def test_modificacion_con_decimales_en_campo_entero_marca_redondeo():
    profile, store = _store([{"code": "A1", "gramos": 10, "nombre": "Uno"}])
    rows = [{"code": "A1", "gramos": "12,5", "nombre": "Uno"}]
    diffs, new_records, obsolete, unchanged = calcular_diferencias(
        store, profile, {"code", "gramos", "nombre"}, rows)
    assert len(diffs) == 1
    assert diffs[0]["redondeos"] == ["gramos"]


def test_alta_con_decimales_en_campo_entero_marca_redondeo():
    profile, store = _store([{"code": "A1", "gramos": 10, "nombre": "Uno"}])
    rows = [{"code": "B2", "gramos": "7,5", "nombre": "Dos"}]
    diffs, new_records, obsolete, unchanged = calcular_diferencias(
        store, profile, {"code", "gramos", "nombre"}, rows)
    assert len(new_records) == 1
    assert new_records[0]["redondeos"] == ["gramos"]


def test_sin_decimales_no_marca_redondeo():
    profile, store = _store([{"code": "A1", "gramos": 10, "nombre": "Uno"}])
    rows = [{"code": "A1", "gramos": "20", "nombre": "Uno"}]
    diffs, new_records, obsolete, unchanged = calcular_diferencias(
        store, profile, {"code", "gramos", "nombre"}, rows)
    assert diffs[0]["redondeos"] == []


def test_placeholder_no_cuenta_como_obsoleto():
    profile, store = _store([{"code": "A1", "gramos": 10, "nombre": "Uno"}])
    rows = []
    # Simula que el único registro del store es un placeholder (no debería
    # aparecer en la lista de obsoletos).
    orig_is_placeholder = store.is_placeholder
    store.is_placeholder = lambda r: True
    try:
        diffs, new_records, obsolete, unchanged = calcular_diferencias(
            store, profile, {"code", "gramos", "nombre"}, rows)
    finally:
        store.is_placeholder = orig_is_placeholder
    assert obsolete == []
