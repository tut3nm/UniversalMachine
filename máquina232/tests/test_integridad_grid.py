"""
test_integridad_grid.py — Nivel 1.6 del plan de mejoras.
============================================================================
Dos riesgos de pérdida/corrupción silenciosa detectados durante el análisis
del motor:

  1. Columnas fantasma: la cantidad de registros se calcula recortando las
     celdas vacías al FINAL de la fila clave. Si otra fila tiene datos más
     allá de esa columna, esas celdas se descartaban sin ningún aviso.
  2. Filas de ancho inconsistente al guardar: si una fila fija queda
     declarada más ancha que la cantidad actual de registros, el archivo
     final podía terminar con filas de largo distinto.
"""

import os
import sys
import tempfile

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "src"))

from profile import Profile  # noqa: E402
from datastore import DataStore  # noqa: E402


def _perfil_columnas():
    data = {
        "id": "synth", "nombre": "Sintético", "descripcion": "",
        "archivo_inicial": "",
        "archivo": {"extension": "csv", "delimitador": ",", "encoding": "utf-8",
                    "bom": False, "fin_de_linea": "CRLF", "orientacion": "columnas"},
        "estructura": {"columna_etiquetas": 0, "primera_columna_datos": 1,
                       "filas_fijas": [{"fila": 0, "celdas": ["META"], "rellenar": True}],
                       "fila_indice": None},
        "campos": [
            {"nombre_interno": "code", "rol": "clave", "fila": 1,
             "etiqueta": "Codigo", "tipo": "texto", "titulo_ui": "Código"},
            {"nombre_interno": "color", "rol": "parametro", "fila": 2,
             "etiqueta": "Color", "tipo": "entero", "titulo_ui": "Color"},
        ],
    }
    return Profile.from_dict(data)


def _escribir(path, filas: list[list[str]]) -> None:
    with open(path, "w", encoding="utf-8", newline="") as f:
        f.write("\r\n".join(",".join(f) for f in filas) + "\r\n")


# -- Columnas fantasma (detección al cargar) ----------------------------------

def test_sin_columnas_fantasma_no_hay_advertencias(tmp_path):
    prof = _perfil_columnas()
    path = tmp_path / "sin_fantasma.csv"
    _escribir(path, [
        ["META"],
        ["Codigo", "A1", "A2"],
        ["Color", "1", "2"],
    ])
    store = DataStore.load(str(path), prof)
    assert len(store.records) == 2
    assert store.advertencias == []


def test_detecta_dato_mas_alla_del_ultimo_registro(tmp_path):
    """La fila clave termina en A2 (columna 2); la fila 'Color' trae un
    tercer valor en la columna 3 que la fila clave no tiene — hoy se
    perdería en silencio."""
    prof = _perfil_columnas()
    path = tmp_path / "con_fantasma.csv"
    _escribir(path, [
        ["META"],
        ["Codigo", "A1", "A2"],
        ["Color", "1", "2", "9"],  # "9" sobra: no hay una 3ra pieza en la fila clave
    ])
    store = DataStore.load(str(path), prof)
    assert len(store.records) == 2, "solo carga 2 registros (los que define la fila clave)"
    assert len(store.advertencias) == 1
    assert "más allá del último registro" in store.advertencias[0]
    assert "'9'" in store.advertencias[0]


def test_detecta_dato_fantasma_en_fila_fija(tmp_path):
    prof = _perfil_columnas()
    path = tmp_path / "fantasma_en_fija.csv"
    _escribir(path, [
        ["META", "", "", "SOBRA"],
        ["Codigo", "A1", "A2"],
        ["Color", "1", "2"],
    ])
    store = DataStore.load(str(path), prof)
    assert len(store.advertencias) == 1
    assert "fila fija" in store.advertencias[0]
    assert "'SOBRA'" in store.advertencias[0]


def test_celda_vacia_mas_alla_del_limite_no_genera_advertencia(tmp_path):
    """Solo importan celdas con contenido real más allá del límite; celdas
    vacías de más no son un dato perdido."""
    prof = _perfil_columnas()
    path = tmp_path / "solo_vacias.csv"
    _escribir(path, [
        ["META"],
        ["Codigo", "A1", "A2"],
        ["Color", "1", "2", ""],  # celda extra pero vacía
    ])
    store = DataStore.load(str(path), prof)
    assert store.advertencias == []


# -- Ancho consistente (verificación al guardar) ------------------------------

def test_guardar_con_fila_fija_mas_ancha_que_los_datos_falla_explicitamente():
    """Si se borran registros hasta quedar por debajo del ancho de una fila
    fija declarada, guardar debe FALLAR con un mensaje claro — nunca dejar
    escribir un archivo con filas de ancho distinto."""
    prof = _perfil_columnas()
    # La fila fija declara 5 celdas (META + 4 más), pero el perfil solo va
    # a tener 2 registros (ancho total 1+2=3): la fila fija queda más ancha.
    prof.filas_fijas = [{"fila": 0, "celdas": ["META", "X", "Y", "Z", "W"],
                        "rellenar": True}]
    store = DataStore(prof, [])
    store.add(store.nuevo_registro({"code": "A1", "color": 1}))
    store.add(store.nuevo_registro({"code": "A2", "color": 2}))

    with pytest.raises(ValueError, match="ancho inconsistente"):
        store.to_grid()

    tmp = os.path.join(tempfile.gettempdir(), "ancho_inconsistente.csv")
    with pytest.raises(ValueError, match="ancho inconsistente"):
        store.save(tmp)
    assert not os.path.exists(tmp), \
        "no debe quedar ningún archivo escrito si la verificación de ancho falla"


def test_guardar_normal_no_se_ve_afectado_por_la_verificacion(tmp_path):
    prof = _perfil_columnas()
    store = DataStore(prof, [])
    store.add(store.nuevo_registro({"code": "A1", "color": 1}))
    store.add(store.nuevo_registro({"code": "A2", "color": 2}))
    tmp = tmp_path / "normal.csv"
    store.save(str(tmp))  # no debe lanzar nada
    store2 = DataStore.load(str(tmp), prof)
    assert len(store2.records) == 2
