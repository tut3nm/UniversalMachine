"""
test_validacion.py — validación de rangos (Nivel 1.3 del plan de mejoras).
============================================================================
"""

import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "src"))

from profile import Profile  # noqa: E402
import validacion  # noqa: E402


def _perfil():
    data = {
        "id": "synth", "nombre": "Sintético", "descripcion": "",
        "archivo_inicial": "",
        "archivo": {"extension": "csv", "delimitador": ",", "encoding": "utf-8",
                    "bom": False, "fin_de_linea": "CRLF", "orientacion": "columnas"},
        "estructura": {"columna_etiquetas": 0, "primera_columna_datos": 1,
                       "filas_fijas": [], "fila_indice": None},
        "campos": [
            {"nombre_interno": "code", "rol": "clave", "fila": 0,
             "etiqueta": "Codigo", "tipo": "texto", "titulo_ui": "Código"},
            {"nombre_interno": "color", "rol": "parametro", "fila": 1,
             "etiqueta": "Color", "tipo": "entero", "titulo_ui": "Color",
             "min": 1, "max": 9, "default": 1},
            {"nombre_interno": "speed", "rol": "parametro", "fila": 2,
             "etiqueta": "Velocidad", "tipo": "entero", "titulo_ui": "Velocidad Inicio",
             "min": 0},
        ],
    }
    return Profile.from_dict(data)


def test_valor_dentro_de_rango_no_da_error():
    prof = _perfil()
    campo_color = prof.campo_por_nombre("color")
    assert validacion.validar_valor_numerico(campo_color, 5) is None


def test_valor_menor_al_minimo():
    prof = _perfil()
    campo_color = prof.campo_por_nombre("color")
    msg = validacion.validar_valor_numerico(campo_color, 0)
    assert msg is not None
    assert "menor" in msg
    assert "Color" in msg


def test_valor_mayor_al_maximo():
    prof = _perfil()
    campo_color = prof.campo_por_nombre("color")
    msg = validacion.validar_valor_numerico(campo_color, 15)
    assert msg is not None
    assert "mayor" in msg


def test_valor_none_no_valida_nada():
    """None representa 'sin dato' (p. ej. celda vacía en el Excel importado):
    no se debe pisar el valor actual, así que tampoco hay nada que validar."""
    prof = _perfil()
    campo_color = prof.campo_por_nombre("color")
    assert validacion.validar_valor_numerico(campo_color, None) is None


def test_campo_sin_max_solo_valida_minimo():
    prof = _perfil()
    campo_speed = prof.campo_por_nombre("speed")
    assert validacion.validar_valor_numerico(campo_speed, 999999) is None
    assert validacion.validar_valor_numerico(campo_speed, -1) is not None


def test_validar_valores_de_registro_detecta_multiples_errores():
    prof = _perfil()
    errores = validacion.validar_valores_de_registro(
        prof, {"code": "A1", "color": 99, "speed": -5})
    campos_con_error = {e.campo for e in errores}
    assert campos_con_error == {"color", "speed"}


def test_validar_valores_de_registro_ignora_la_clave():
    prof = _perfil()
    errores = validacion.validar_valores_de_registro(prof, {"code": "", "color": 5, "speed": 10})
    assert errores == [], "la clave no se valida acá (la resuelve cada llamador)"


def test_validar_valores_de_registro_sin_errores():
    prof = _perfil()
    errores = validacion.validar_valores_de_registro(
        prof, {"code": "A1", "color": 5, "speed": 350})
    assert errores == []


def test_validar_valores_de_registro_ignora_campos_ausentes():
    """Simula el caso de la importación de Excel: solo se mapean/validan los
    campos que efectivamente vinieron en el Excel (los demás ni aparecen en
    `valores`)."""
    prof = _perfil()
    errores = validacion.validar_valores_de_registro(prof, {"code": "A1", "color": 99})
    assert {e.campo for e in errores} == {"color"}


# -- parsear_valor_campo (Nivel 4.8: edición en línea / edición masiva) --------
def test_parsear_clave_vacia_es_error():
    prof = _perfil()
    valor, error = validacion.parsear_valor_campo(prof.campo_por_nombre("code"), "  ")
    assert valor is None
    assert "vacío" in error


def test_parsear_clave_valida():
    prof = _perfil()
    valor, error = validacion.parsear_valor_campo(prof.campo_por_nombre("code"), " A1 ")
    assert valor == "A1"
    assert error is None


def test_parsear_numerico_valido():
    prof = _perfil()
    valor, error = validacion.parsear_valor_campo(prof.campo_por_nombre("color"), "5")
    assert valor == 5
    assert error is None


def test_parsear_numerico_fuera_de_rango():
    prof = _perfil()
    valor, error = validacion.parsear_valor_campo(prof.campo_por_nombre("color"), "99")
    assert valor is None
    assert "mayor" in error


def test_parsear_numerico_no_numerico_es_error():
    prof = _perfil()
    valor, error = validacion.parsear_valor_campo(prof.campo_por_nombre("color"), "abc")
    assert valor is None
    assert "número" in error


def test_parsear_numerico_vacio_usa_default():
    prof = _perfil()
    valor, error = validacion.parsear_valor_campo(prof.campo_por_nombre("color"), "")
    assert valor == 1  # default del campo "color"
    assert error is None


def test_parsear_numerico_acepta_coma_decimal():
    prof = _perfil()
    valor, error = validacion.parsear_valor_campo(prof.campo_por_nombre("speed"), "3,0")
    assert valor == 3
    assert error is None


def test_parsear_texto_no_clave_pasa_tal_cual():
    data = {
        "id": "synth2", "nombre": "Sintético 2", "descripcion": "",
        "archivo_inicial": "",
        "archivo": {"extension": "csv", "delimitador": ",", "encoding": "utf-8",
                    "bom": False, "fin_de_linea": "CRLF", "orientacion": "filas"},
        "estructura": {"fila_encabezado": 0, "primera_fila_datos": 1},
        "campos": [
            {"nombre_interno": "code", "rol": "clave", "columna": 0,
             "etiqueta": "Codigo", "tipo": "texto", "titulo_ui": "Código"},
            {"nombre_interno": "nombre", "rol": "parametro", "columna": 1,
             "etiqueta": "Nombre", "tipo": "texto", "titulo_ui": "Nombre"},
        ],
    }
    prof = Profile.from_dict(data)
    valor, error = validacion.parsear_valor_campo(prof.campo_por_nombre("nombre"), "  Tapa Azul  ")
    assert valor == "Tapa Azul"
    assert error is None
