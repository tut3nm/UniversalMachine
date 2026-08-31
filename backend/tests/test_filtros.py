"""Tests de src/filtros.py (Nivel 4.7: búsqueda y filtros avanzados)."""

import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "app", "core"))

from profile import Profile  # noqa: E402
import filtros  # noqa: E402


def _campos():
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
             "min": 0, "max": 100},
            {"nombre_interno": "nombre", "rol": "parametro", "columna": 2,
             "etiqueta": "Nombre", "tipo": "texto", "titulo_ui": "Nombre"},
        ],
    }
    return Profile.from_dict(data).campos_visibles()


# -- coincide_busqueda ----------------------------------------------------------
def test_busqueda_vacia_coincide_siempre():
    campos = _campos()
    assert filtros.coincide_busqueda({"code": "A1", "nombre": "Tapa"}, campos, "") is True


def test_busqueda_por_codigo():
    campos = _campos()
    assert filtros.coincide_busqueda({"code": "A1", "nombre": "Tapa"}, campos, "a1") is True


def test_busqueda_por_otro_campo_no_solo_codigo():
    campos = _campos()
    rec = {"code": "X9", "gramos": 10, "nombre": "Tapa Azul"}
    assert filtros.coincide_busqueda(rec, campos, "azul") is True
    assert filtros.coincide_busqueda(rec, campos, "verde") is False


# -- coincide_rangos --------------------------------------------------------------
def test_sin_rangos_coincide_siempre():
    assert filtros.coincide_rangos({"gramos": 10}, {}) is True


def test_rango_dentro_del_limite():
    assert filtros.coincide_rangos({"gramos": 25}, {"gramos": (20, 40)}) is True


def test_rango_fuera_por_abajo():
    assert filtros.coincide_rangos({"gramos": 5}, {"gramos": (20, 40)}) is False


def test_rango_fuera_por_arriba():
    assert filtros.coincide_rangos({"gramos": 99}, {"gramos": (20, 40)}) is False


def test_rango_sin_minimo_o_sin_maximo():
    assert filtros.coincide_rangos({"gramos": 5}, {"gramos": (None, 40)}) is True
    assert filtros.coincide_rangos({"gramos": 999}, {"gramos": (20, None)}) is True


def test_rango_con_valor_ausente_no_coincide():
    assert filtros.coincide_rangos({}, {"gramos": (20, 40)}) is False


# -- filtrar (búsqueda + rangos combinados) --------------------------------------
def test_filtrar_combina_busqueda_y_rango():
    campos = _campos()
    records = [
        {"code": "A1", "gramos": 30, "nombre": "Tapa Azul"},
        {"code": "A2", "gramos": 5, "nombre": "Tapa Roja"},
        {"code": "B1", "gramos": 35, "nombre": "Base Azul"},
    ]
    resultado = filtros.filtrar(records, campos, "azul", {"gramos": (20, 40)})
    assert [r["code"] for r in resultado] == ["A1", "B1"]


# -- filtros guardados (persistencia) --------------------------------------------
def test_cargar_guardados_sin_archivo_es_vacio(tmp_path):
    assert filtros.cargar_guardados(str(tmp_path)) == []


def test_agregar_y_cargar_preset(tmp_path):
    filtros.agregar_o_reemplazar(str(tmp_path), "Livianos", "",
                                 {"gramos": (0, 20)})
    guardados = filtros.cargar_guardados(str(tmp_path))
    assert len(guardados) == 1
    assert guardados[0]["nombre"] == "Livianos"
    assert guardados[0]["rangos"]["gramos"] == [0, 20]


def test_agregar_con_mismo_nombre_reemplaza(tmp_path):
    filtros.agregar_o_reemplazar(str(tmp_path), "X", "a", {"gramos": (0, 10)})
    filtros.agregar_o_reemplazar(str(tmp_path), "X", "b", {"gramos": (5, 15)})
    guardados = filtros.cargar_guardados(str(tmp_path))
    assert len(guardados) == 1
    assert guardados[0]["busqueda"] == "b"


def test_eliminar_preset(tmp_path):
    filtros.agregar_o_reemplazar(str(tmp_path), "X", "", {})
    filtros.agregar_o_reemplazar(str(tmp_path), "Y", "", {})
    restantes = filtros.eliminar(str(tmp_path), "X")
    assert [p["nombre"] for p in restantes] == ["Y"]
    assert [p["nombre"] for p in filtros.cargar_guardados(str(tmp_path))] == ["Y"]


def test_cargar_guardados_archivo_corrupto_es_vacio(tmp_path):
    (tmp_path / filtros.NOMBRE_ARCHIVO).write_text("{no es json", encoding="utf-8")
    assert filtros.cargar_guardados(str(tmp_path)) == []
