"""Tests de src/importacion.py (calcular_diferencias), extraído de
ImportDialog._compute_diffs en el Nivel 3.1 del plan de mejoras.

Desde PLAN_IMPORTACION_CLAVE_BUSQUEDA.md la búsqueda se hace por un campo
elegido (no necesariamente la PK)."""

import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "app", "core"))

from profile import Profile  # noqa: E402
from datastore import DataStore  # noqa: E402
from importacion import calcular_diferencias  # noqa: E402

MAPEADOS = {"gramos", "nombre"}


def _perfil(sintetico_id=False):
    campos = [
        {"nombre_interno": "code", "rol": "clave", "columna": 0,
         "etiqueta": "Codigo", "tipo": "texto", "titulo_ui": "Código"},
        {"nombre_interno": "gramos", "rol": "parametro", "columna": 1,
         "etiqueta": "Gramos", "tipo": "entero", "titulo_ui": "Gramos",
         "min": 0, "max": 100, "default": 0},
        {"nombre_interno": "nombre", "rol": "parametro", "columna": 2,
         "etiqueta": "Nombre", "tipo": "texto", "titulo_ui": "Nombre"},
    ]
    if sintetico_id:
        campos[0]["rol"] = "parametro"
        campos.insert(0, {"nombre_interno": "id", "rol": "clave", "tipo": "entero",
                          "titulo_ui": "ID", "etiqueta": "__ID_AUTO__",
                          "sintetica": True})
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


def _store(records, perfil=None):
    profile = perfil or _perfil()
    return profile, DataStore(profile, records)


def test_registro_modificado_se_detecta_como_diff():
    profile, store = _store([{"code": "A1", "gramos": 10, "nombre": "Uno"}])
    rows = [{"code": "A1", "gramos": "20", "nombre": "Uno"}]
    r = calcular_diferencias(store, profile, "code", MAPEADOS, rows)
    assert len(r["diffs"]) == 1
    assert r["diffs"][0]["id"] == "A1"
    assert r["diffs"][0]["busqueda"] == "A1"
    assert r["diffs"][0]["new"]["gramos"] == 20
    assert r["diffs"][0]["old"]["gramos"] == 10
    assert not r["diffs"][0]["errores"]
    assert r["sin_coincidencia"] == []
    assert r["obsoletos"] == []
    assert r["sin_cambios"] == 0


def test_registro_sin_cambios_cuenta_como_sin_cambios():
    profile, store = _store([{"code": "A1", "gramos": 10, "nombre": "Uno"}])
    rows = [{"code": "A1", "gramos": "10", "nombre": "Uno"}]
    r = calcular_diferencias(store, profile, "code", MAPEADOS, rows)
    assert r["diffs"] == []
    assert r["sin_cambios"] == 1


def test_codigo_del_excel_sin_coincidencia_es_solo_aviso():
    profile, store = _store([{"code": "A1", "gramos": 10, "nombre": "Uno"}])
    rows = [{"code": "A1", "gramos": "10", "nombre": "Uno"},
            {"code": "B2", "gramos": "5", "nombre": "Dos"}]
    r = calcular_diferencias(store, profile, "code", MAPEADOS, rows)
    assert r["sin_coincidencia"] == [{"codigo": "B2"}]
    assert r["diffs"] == []


def test_codigo_ausente_del_excel_se_detecta_como_obsoleto():
    profile, store = _store([{"code": "A1", "gramos": 10, "nombre": "Uno"},
                              {"code": "B2", "gramos": 5, "nombre": "Dos"}])
    rows = [{"code": "A1", "gramos": "10", "nombre": "Uno"}]
    r = calcular_diferencias(store, profile, "code", MAPEADOS, rows)
    assert len(r["obsoletos"]) == 1
    assert r["obsoletos"][0]["id"] == "B2"


def test_valor_fuera_de_rango_se_marca_con_errores():
    profile, store = _store([{"code": "A1", "gramos": 10, "nombre": "Uno"}])
    rows = [{"code": "A1", "gramos": "999", "nombre": "Uno"}]
    r = calcular_diferencias(store, profile, "code", MAPEADOS, rows)
    assert len(r["diffs"]) == 1
    assert r["diffs"][0]["errores"]


def test_modificacion_con_decimales_en_campo_entero_marca_redondeo():
    profile, store = _store([{"code": "A1", "gramos": 10, "nombre": "Uno"}])
    rows = [{"code": "A1", "gramos": "12,5", "nombre": "Uno"}]
    r = calcular_diferencias(store, profile, "code", MAPEADOS, rows)
    assert r["diffs"][0]["redondeos"] == ["gramos"]


def test_sin_decimales_no_marca_redondeo():
    profile, store = _store([{"code": "A1", "gramos": 10, "nombre": "Uno"}])
    rows = [{"code": "A1", "gramos": "20", "nombre": "Uno"}]
    r = calcular_diferencias(store, profile, "code", MAPEADOS, rows)
    assert r["diffs"][0]["redondeos"] == []


def test_placeholder_no_cuenta_como_obsoleto():
    perfil = _perfil()
    perfil.features = {"placeholder": {"patron": "^A\\d$", "generar": "A{n}"}}
    store = DataStore(perfil, [{"code": "A1", "gramos": 10, "nombre": "Uno"},
                               {"code": "B2", "gramos": 5, "nombre": "Dos"}])
    r = calcular_diferencias(store, perfil, "code", MAPEADOS, [])
    assert [o["id"] for o in r["obsoletos"]] == ["B2"]


def test_busqueda_por_campo_que_no_es_la_pk():
    # Con ID automático la PK es "id"; el cruce se hace por "code".
    perfil = _perfil(sintetico_id=True)
    store = DataStore(perfil, [
        {"id": 1, "code": "A1", "gramos": 10, "nombre": "Uno"},
        {"id": 2, "code": "B2", "gramos": 5, "nombre": "Dos"},
    ])
    rows = [{"code": "B2", "gramos": "7", "nombre": "Dos"}]
    r = calcular_diferencias(store, perfil, "code", MAPEADOS, rows)
    assert len(r["diffs"]) == 1
    assert r["diffs"][0]["id"] == "2"        # la PK identifica el registro
    assert r["diffs"][0]["busqueda"] == "B2"
    assert r["diffs"][0]["new"]["gramos"] == 7
    assert [o["id"] for o in r["obsoletos"]] == ["1"]


def test_clave_repetida_en_el_excel_es_conflicto():
    profile, store = _store([{"code": "A1", "gramos": 10, "nombre": "Uno"}])
    rows = [{"code": "A1", "gramos": "20", "nombre": "Uno"},
            {"code": "A1", "gramos": "30", "nombre": "Uno"}]
    r = calcular_diferencias(store, profile, "code", MAPEADOS, rows)
    assert r["diffs"] == []
    assert r["conflictos"] == [{"codigo": "A1", "motivo": "aparece 2 veces en el archivo"}]
    # El registro sigue emparejado: no es obsoleto.
    assert r["obsoletos"] == []


def test_clave_repetida_en_el_sistema_es_conflicto():
    profile, store = _store([{"code": "A1", "gramos": 10, "nombre": "Uno"},
                              {"code": "A1", "gramos": 11, "nombre": "Dos"}])
    rows = [{"code": "A1", "gramos": "20", "nombre": "Uno"}]
    r = calcular_diferencias(store, profile, "code", MAPEADOS, rows)
    assert r["diffs"] == []
    assert r["conflictos"] == [
        {"codigo": "A1", "motivo": "2 registros del sistema tienen este código"}]


def test_celda_vacia_no_cuenta_como_cambio():
    profile, store = _store([{"code": "A1", "gramos": 10, "nombre": "Uno"}])
    rows = [{"code": "A1", "gramos": None, "nombre": "Uno"}]
    r = calcular_diferencias(store, profile, "code", MAPEADOS, rows)
    assert r["diffs"] == []
    assert r["sin_cambios"] == 1


def test_filas_sin_clave_se_cuentan_y_no_se_usan():
    profile, store = _store([{"code": "A1", "gramos": 10, "nombre": "Uno"}])
    rows = [{"code": None, "gramos": "20", "nombre": "x"},
            {"code": "  ", "gramos": "20", "nombre": "x"}]
    r = calcular_diferencias(store, profile, "code", MAPEADOS, rows)
    assert r["filas_sin_clave"] == 2
    assert r["sin_coincidencia"] == []
    assert len(r["obsoletos"]) == 1


def test_clave_numerica_compara_por_valor():
    # "010" del Excel coincide con 10 del catálogo (campo entero).
    profile, store = _store([{"code": "A1", "gramos": 10, "nombre": "Uno"}])
    rows = [{"code": "x", "gramos": "20", "nombre": "Uno"}]
    r = calcular_diferencias(store, profile, "gramos", {"nombre"}, rows)
    assert r["sin_coincidencia"] == [{"codigo": "20"}]
    rows2 = [{"code": "A1", "gramos": "010", "nombre": "Uno"}]
    r2 = calcular_diferencias(store, profile, "gramos", {"code", "nombre"}, rows2)
    assert r2["sin_coincidencia"] == []
    assert r2["sin_cambios"] == 1
