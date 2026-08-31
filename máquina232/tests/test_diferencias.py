"""Tests de src/diferencias.py (Nivel 4.1: vista de diferencias contra el
original)."""

import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "src"))

from profile import Profile  # noqa: E402
from datastore import DataStore  # noqa: E402
from diferencias import comparar_con_original, filtrar_por_tipo, a_filas_csv  # noqa: E402


def _perfil(con_placeholder=False):
    features = {}
    if con_placeholder:
        features["placeholder"] = {"patron": r"^_VACIO_\d+$", "generar": "_VACIO_{n}"}
    data = {
        "id": "synth", "nombre": "Sintético", "descripcion": "", "archivo_inicial": "",
        "archivo": {"extension": "csv", "delimitador": ",", "encoding": "utf-8",
                    "bom": False, "fin_de_linea": "LF", "orientacion": "filas"},
        "estructura": {"fila_encabezado": 0, "primera_fila_datos": 1},
        "campos": [
            {"nombre_interno": "code", "rol": "clave", "columna": 0,
             "etiqueta": "Codigo", "tipo": "texto", "titulo_ui": "Código"},
            {"nombre_interno": "gramos", "rol": "parametro", "columna": 1,
             "etiqueta": "Gramos", "tipo": "entero", "titulo_ui": "Gramos",
             "min": 0, "max": 100, "default": 0},
        ],
        "features": features,
    }
    return Profile.from_dict(data)


def test_sin_cambios_no_devuelve_diffs():
    profile = _perfil()
    actual = DataStore(profile, [{"code": "A1", "gramos": 10}])
    original = DataStore(profile, [{"code": "A1", "gramos": 10}])
    assert comparar_con_original(actual, original) == []


def test_alta_se_detecta():
    profile = _perfil()
    actual = DataStore(profile, [{"code": "A1", "gramos": 10}, {"code": "B2", "gramos": 5}])
    original = DataStore(profile, [{"code": "A1", "gramos": 10}])
    diffs = comparar_con_original(actual, original)
    assert len(diffs) == 1
    assert diffs[0]["tipo"] == "alta"
    assert diffs[0]["code"] == "B2"
    assert diffs[0]["anteriores"] is None


def test_baja_se_detecta():
    profile = _perfil()
    actual = DataStore(profile, [{"code": "A1", "gramos": 10}])
    original = DataStore(profile, [{"code": "A1", "gramos": 10}, {"code": "B2", "gramos": 5}])
    diffs = comparar_con_original(actual, original)
    assert len(diffs) == 1
    assert diffs[0]["tipo"] == "baja"
    assert diffs[0]["code"] == "B2"
    assert diffs[0]["nuevos"] is None


def test_modificacion_lista_campos_modificados():
    profile = _perfil()
    actual = DataStore(profile, [{"code": "A1", "gramos": 20}])
    original = DataStore(profile, [{"code": "A1", "gramos": 10}])
    diffs = comparar_con_original(actual, original)
    assert len(diffs) == 1
    assert diffs[0]["tipo"] == "modificacion"
    assert diffs[0]["campos_modificados"] == ["gramos"]
    assert diffs[0]["anteriores"]["gramos"] == 10
    assert diffs[0]["nuevos"]["gramos"] == 20


def test_placeholders_no_se_comparan():
    profile = _perfil(con_placeholder=True)
    actual = DataStore(profile, [{"code": "_VACIO_1", "gramos": 0}, {"code": "A1", "gramos": 10}])
    original = DataStore(profile, [{"code": "_VACIO_1", "gramos": 0}])
    diffs = comparar_con_original(actual, original)
    assert len(diffs) == 1
    assert diffs[0]["code"] == "A1"


def test_filtrar_por_tipo():
    profile = _perfil()
    actual = DataStore(profile, [{"code": "A1", "gramos": 20}, {"code": "B2", "gramos": 5}])
    original = DataStore(profile, [{"code": "A1", "gramos": 10}])
    diffs = comparar_con_original(actual, original)
    solo_altas = filtrar_por_tipo(diffs, {"alta"})
    assert len(solo_altas) == 1
    assert solo_altas[0]["tipo"] == "alta"


def test_a_filas_csv_incluye_encabezado_y_valores():
    profile = _perfil()
    actual = DataStore(profile, [{"code": "A1", "gramos": 20}])
    original = DataStore(profile, [{"code": "A1", "gramos": 10}])
    diffs = comparar_con_original(actual, original)
    filas = a_filas_csv(profile, diffs)
    assert filas[0] == ["tipo", "codigo", "Gramos (antes)", "Gramos (ahora)"]
    assert filas[1] == ["modificacion", "A1", "10", "20"]
