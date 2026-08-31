"""Tests de src/salud.py (Nivel 4.5: reporte de salud del catálogo)."""

import os
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "app", "core"))

from profile import Profile  # noqa: E402
from datastore import DataStore  # noqa: E402
from metadata import Sidecar  # noqa: E402
from salud import evaluar_salud, contar_slots_libres  # noqa: E402


def _perfil(con_placeholder=False, con_duplicados=False):
    features = {}
    if con_placeholder:
        features["placeholder"] = {"patron": r"^_VACIO_\d+$", "generar": "_VACIO_{n}"}
    if con_duplicados:
        features["duplicados"] = {"metodo": "ignorar_ceros"}
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
            {"nombre_interno": "nombre", "rol": "parametro", "columna": 2,
             "etiqueta": "Nombre", "tipo": "texto", "titulo_ui": "Nombre"},
        ],
        "features": features,
    }
    return Profile.from_dict(data)


def _sidecar_vacio():
    tmp = os.path.join(tempfile.gettempdir(), f"salud_test_meta_{os.getpid()}.json")
    if os.path.exists(tmp):
        os.remove(tmp)
    return Sidecar.load(tmp)


def test_valor_fuera_de_rango_se_detecta():
    profile = _perfil()
    store = DataStore(profile, [{"code": "A1", "gramos": 999, "nombre": "Uno"}])
    hallazgos = evaluar_salud(store, _sidecar_vacio())
    assert any(h.tipo == "fuera_de_rango" and h.code == "A1" for h in hallazgos)


def test_campo_vacio_se_detecta():
    profile = _perfil()
    store = DataStore(profile, [{"code": "A1", "gramos": 10, "nombre": ""}])
    hallazgos = evaluar_salud(store, _sidecar_vacio())
    assert any(h.tipo == "campo_vacio" and h.code == "A1" for h in hallazgos)


def test_registro_sano_no_genera_hallazgos():
    profile = _perfil()
    store = DataStore(profile, [{"code": "A1", "gramos": 10, "nombre": "Uno"}])
    assert evaluar_salud(store, _sidecar_vacio()) == []


def test_placeholder_no_genera_hallazgos():
    profile = _perfil(con_placeholder=True)
    store = DataStore(profile, [{"code": "_VACIO_1", "gramos": 0, "nombre": ""}])
    assert evaluar_salud(store, _sidecar_vacio()) == []


def test_slots_libres_cuenta_placeholders():
    profile = _perfil(con_placeholder=True)
    store = DataStore(profile, [{"code": "_VACIO_1", "gramos": 0, "nombre": ""},
                                {"code": "_VACIO_2", "gramos": 0, "nombre": ""},
                                {"code": "A1", "gramos": 10, "nombre": "Uno"}])
    assert contar_slots_libres(store) == 2


def test_slots_libres_es_cero_sin_placeholder_configurado():
    profile = _perfil()
    store = DataStore(profile, [{"code": "A1", "gramos": 10, "nombre": "Uno"}])
    assert contar_slots_libres(store) == 0


def test_duplicado_sin_revisar_se_detecta_y_marca_como_revisado_lo_excluye():
    profile = _perfil(con_duplicados=True)
    store = DataStore(profile, [{"code": "A100", "gramos": 10, "nombre": "Uno"},
                                {"code": "A001", "gramos": 20, "nombre": "Dos"}])
    sidecar = _sidecar_vacio()
    hallazgos = evaluar_salud(store, sidecar)
    assert any(h.tipo == "duplicado" for h in hallazgos)

    sidecar.set("A100", "no_duplicado", True)
    sidecar.set("A001", "no_duplicado", True)
    hallazgos_tras_revisar = evaluar_salud(store, sidecar)
    assert not any(h.tipo == "duplicado" for h in hallazgos_tras_revisar)
