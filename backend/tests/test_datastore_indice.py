"""Tests del índice clave->posición de find_key() (Nivel 5: find_key era
O(n), llamado dentro del bucle de la importación)."""

import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "app", "core"))

from profile import Profile  # noqa: E402
from datastore import DataStore  # noqa: E402


def _perfil():
    data = {
        "id": "synth", "nombre": "Sintético", "descripcion": "", "archivo_inicial": "",
        "archivo": {"extension": "csv", "delimitador": ",", "encoding": "utf-8",
                    "bom": False, "fin_de_linea": "LF", "orientacion": "filas"},
        "estructura": {"fila_encabezado": 0, "primera_fila_datos": 1},
        "campos": [
            {"nombre_interno": "code", "rol": "clave", "columna": 0,
             "etiqueta": "Codigo", "tipo": "texto", "titulo_ui": "Código"},
            {"nombre_interno": "gramos", "rol": "parametro", "columna": 1,
             "etiqueta": "Gramos", "tipo": "entero", "titulo_ui": "Gramos"},
        ],
    }
    return Profile.from_dict(data)


def test_find_key_basico():
    profile = _perfil()
    store = DataStore(profile, [{"code": "A1", "gramos": 10}, {"code": "B2", "gramos": 20}])
    assert store.find_key("A1") == 0
    assert store.find_key("B2") == 1
    assert store.find_key("Z9") == -1


def test_find_key_usa_el_mismo_indice_en_llamadas_repetidas():
    """El índice se construye una vez y se reutiliza — verificamos que
    seguir llamando find_key() no lo reconstruye de más (comportamiento
    observable: sigue devolviendo lo mismo tras mutar el objeto interno
    _indice_claves entre llamadas, si no se invalidó)."""
    profile = _perfil()
    store = DataStore(profile, [{"code": "A1", "gramos": 10}])
    assert store.find_key("A1") == 0
    assert store._indice_claves is not None
    # Envenenamos el índice a mano para probar que efectivamente se usa
    # (si find_key volviera a recorrer la lista, ignoraría este cambio).
    store._indice_claves["A1"] = 99
    assert store.find_key("A1") == 99


def test_add_actualiza_el_indice_sin_invalidarlo():
    profile = _perfil()
    store = DataStore(profile, [{"code": "A1", "gramos": 10}])
    store.find_key("A1")  # fuerza la construcción del índice
    nuevo = store.nuevo_registro({"code": "B2", "gramos": 20})
    store.add(nuevo)
    assert store._indice_claves is not None, "add() no debería invalidar el índice"
    assert store.find_key("B2") == 1


def test_update_de_clave_invalida_el_indice():
    profile = _perfil()
    store = DataStore(profile, [{"code": "A1", "gramos": 10}, {"code": "B2", "gramos": 20}])
    store.find_key("A1")
    store.update(0, {"code": "A1-renombrado"})
    assert store.find_key("A1") == -1
    assert store.find_key("A1-renombrado") == 0


def test_update_sin_tocar_la_clave_no_rompe_el_indice():
    profile = _perfil()
    store = DataStore(profile, [{"code": "A1", "gramos": 10}])
    store.find_key("A1")
    store.update(0, {"gramos": 99})
    assert store.find_key("A1") == 0
    assert store.records[0]["gramos"] == 99


def test_delete_invalida_el_indice_y_las_posiciones_se_recalculan():
    profile = _perfil()
    store = DataStore(profile, [{"code": "A1", "gramos": 10},
                                {"code": "B2", "gramos": 20},
                                {"code": "C3", "gramos": 30}])
    store.find_key("C3")  # construye el índice con C3 en la posición 2
    store.delete(0)  # borra A1: B2 y C3 corren una posición hacia atrás
    assert store.find_key("B2") == 0
    assert store.find_key("C3") == 1


def test_find_key_con_claves_duplicadas_devuelve_la_primera_posicion():
    """Antes de resolver duplicados con el diálogo correspondiente, el
    catálogo puede tener temporalmente dos registros con la misma clave.
    find_key() sin exclude_index debe devolver la PRIMERA posición, igual
    que el recorrido lineal que reemplaza el índice."""
    profile = _perfil()
    store = DataStore(profile, [{"code": "A1", "gramos": 10},
                                {"code": "A1", "gramos": 20}])
    assert store.find_key("A1") == 0


def test_find_key_con_exclude_index_no_usa_el_indice_cacheado():
    profile = _perfil()
    store = DataStore(profile, [{"code": "A1", "gramos": 10}, {"code": "A2", "gramos": 20}])
    store.find_key("A1")  # construye el índice
    assert store.find_key("A1", exclude_index=0) == -1
    assert store.find_key("A2", exclude_index=1) == -1
    assert store.find_key("A2", exclude_index=0) == 1
