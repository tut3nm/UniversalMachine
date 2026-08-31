"""
test_profile_validacion.py — Nivel 1.7 del plan de mejoras.
============================================================================
Antes, un perfil con un regex de placeholder inválido no fallaba al
cargarlo (ProfileError, con la fila/motivo claro) sino recién en el primer
uso, con un re.error crudo en medio del refresco de la tabla. Tampoco se
validaba coherencia de min/max/default/formato ni que 'fila' fuera un
entero. Este archivo cubre esos casos.
"""

import os
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "src"))

from profile import Profile, ProfileError  # noqa: E402


def _base(**overrides) -> dict:
    data = {
        "id": "x", "nombre": "X", "descripcion": "",
        "archivo": {"orientacion": "columnas", "delimitador": ",",
                    "fin_de_linea": "CRLF"},
        "estructura": {"columna_etiquetas": 0, "primera_columna_datos": 1,
                       "filas_fijas": [], "fila_indice": None},
        "campos": [
            {"nombre_interno": "code", "rol": "clave", "fila": 0,
             "etiqueta": "Codigo", "tipo": "texto", "titulo_ui": "Código"},
            {"nombre_interno": "color", "rol": "parametro", "fila": 1,
             "etiqueta": "Color", "tipo": "entero", "titulo_ui": "Color"},
        ],
        "features": {},
    }
    data.update(overrides)
    return data


# -- Placeholder regex/plantilla -----------------------------------------------

def test_regex_de_placeholder_invalido_falla_al_cargar_no_al_usarlo():
    data = _base(features={"placeholder": {"patron": "(", "generar": "_X_{n}"}})
    with pytest.raises(ProfileError, match="regex"):
        Profile.from_dict(data)


def test_regex_de_placeholder_valido_no_falla():
    data = _base(features={"placeholder": {"patron": r"^_X_\d+$", "generar": "_X_{n}"}})
    prof = Profile.from_dict(data)
    assert prof.placeholder_regex().match("_X_3")


def test_plantilla_generar_invalida_falla_al_cargar():
    data = _base(features={"placeholder": {"patron": r"^_X_\d+$", "generar": "_X_{n_mal_escrito}"}})
    with pytest.raises(ProfileError, match="plantilla"):
        Profile.from_dict(data)


# -- Coherencia min/max/default ------------------------------------------------

def test_min_mayor_que_max_falla():
    data = _base()
    data["campos"][1]["min"] = 10
    data["campos"][1]["max"] = 5
    with pytest.raises(ProfileError, match="min.*max"):
        Profile.from_dict(data)


def test_default_menor_que_min_falla():
    data = _base()
    data["campos"][1]["min"] = 1
    data["campos"][1]["default"] = 0
    with pytest.raises(ProfileError, match="default"):
        Profile.from_dict(data)


def test_default_mayor_que_max_falla():
    data = _base()
    data["campos"][1]["max"] = 9
    data["campos"][1]["default"] = 15
    with pytest.raises(ProfileError, match="default"):
        Profile.from_dict(data)


def test_default_no_numerico_en_campo_numerico_falla():
    data = _base()
    data["campos"][1]["default"] = "no-es-numero"
    with pytest.raises(ProfileError, match="default"):
        Profile.from_dict(data)


def test_default_dentro_de_rango_no_falla():
    data = _base()
    data["campos"][1]["min"] = 1
    data["campos"][1]["max"] = 9
    data["campos"][1]["default"] = 5
    prof = Profile.from_dict(data)
    assert prof.campo_por_nombre("color").default == 5


# -- formato.ancho / formato.decimales -----------------------------------------

def test_ancho_negativo_en_entero_ceros_falla():
    data = _base()
    data["campos"][1]["tipo"] = "entero_ceros"
    data["campos"][1]["formato"] = {"ancho": -3}
    with pytest.raises(ProfileError, match="ancho"):
        Profile.from_dict(data)


def test_ancho_no_entero_en_entero_ceros_falla():
    data = _base()
    data["campos"][1]["tipo"] = "entero_ceros"
    data["campos"][1]["formato"] = {"ancho": "doce"}
    with pytest.raises(ProfileError, match="ancho"):
        Profile.from_dict(data)


def test_decimales_negativos_falla():
    data = _base()
    data["campos"][1]["tipo"] = "decimal"
    data["campos"][1]["formato"] = {"decimales": -1}
    with pytest.raises(ProfileError, match="decimales"):
        Profile.from_dict(data)


# -- 'fila' debe ser entero (orientacion columnas) -----------------------------

def test_fila_como_string_falla():
    data = _base()
    data["campos"][1]["fila"] = "1"  # string en vez de int
    with pytest.raises(ProfileError, match="entero"):
        Profile.from_dict(data)


def test_fila_booleana_falla():
    """bool es subclase de int en Python: True/False no deben colarse como
    número de fila válido."""
    data = _base()
    data["campos"][1]["fila"] = True
    with pytest.raises(ProfileError, match="entero"):
        Profile.from_dict(data)
