"""Tests del listado de registros con búsqueda, rangos, orden y ventana
resueltos en el servidor (B18/B19 de PLAN_PARIDAD_UI.md), y de la caché de
lectura que evita reparsear el CSV en cada scroll de la tabla.

Se llama al servicio directamente: lo que interesa verificar es el criterio
de filtrado y orden (que tiene que ser el mismo del escritorio), no el
ruteo de FastAPI.
"""

import json
import os
import sys
import time

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "app", "core"))

import paths  # noqa: E402
from datastore import DataStore  # noqa: E402
from app.services import maquinas_service as svc  # noqa: E402

MACHINE_ID = "sintetica"


def _perfil() -> dict:
    return {
        "id": MACHINE_ID,
        "nombre": "Máquina sintética",
        "descripcion": "catálogo generado para tests",
        "archivo_inicial": "",
        "archivo": {
            "extension": "csv",
            "delimitador": ",",
            "encoding": "utf-8",
            "bom": False,
            "fin_de_linea": "CRLF",
            "orientacion": "filas",
        },
        "estructura": {"fila_encabezado": 0, "primera_fila_datos": 1},
        "campos": [
            {"nombre_interno": "code", "rol": "clave", "tipo": "texto",
             "titulo_ui": "Código", "columna": 0, "etiqueta": "Codigo"},
            {"nombre_interno": "grams", "rol": "parametro", "tipo": "entero",
             "titulo_ui": "Gramos", "columna": 1, "etiqueta": "Gramos",
             "min": 0, "max": 999},
            {"nombre_interno": "nombre", "rol": "parametro", "tipo": "texto",
             "titulo_ui": "Nombre", "columna": 2, "etiqueta": "Nombre"},
        ],
        "features": {
            "placeholder": {"patron": r"^_VACIO_\d+$", "generar": "_VACIO_{n}"},
        },
    }


def _filas(n_reales: int, n_placeholders: int) -> list[str]:
    filas = ["Codigo,Gramos,Nombre"]
    for i in range(n_reales):
        # Gramos baja mientras el código sube: así un test que ordena por
        # gramos no puede pasar por accidente con el orden del archivo.
        filas.append(f"C{i:05d},{n_reales - i},Pieza {chr(65 + i % 26)}{i}")
    for j in range(n_placeholders):
        filas.append(f"_VACIO_{j},0,")
    return filas


def _crear_maquina(base: str, n_reales: int = 12, n_placeholders: int = 3) -> None:
    pdir = os.path.join(base, "profiles")
    os.makedirs(pdir, exist_ok=True)
    with open(os.path.join(pdir, f"maquina_{MACHINE_ID}.json"), "w",
              encoding="utf-8") as f:
        json.dump(_perfil(), f, ensure_ascii=False)

    ddir = os.path.join(base, "datos", MACHINE_ID)
    os.makedirs(ddir, exist_ok=True)
    contenido = "\r\n".join(_filas(n_reales, n_placeholders)) + "\r\n"
    for nombre in ("actual.csv", "original.csv"):
        with open(os.path.join(ddir, nombre), "w", encoding="utf-8", newline="") as f:
            f.write(contenido)


@pytest.fixture
def maquina(tmp_path, monkeypatch):
    """Máquina sintética aislada en tmp_path, con 12 registros reales y 3
    slots vacíos."""
    base = str(tmp_path)
    monkeypatch.setattr(paths, "app_base_dir", lambda: base)
    svc._CACHE_LECTURA.clear()
    _crear_maquina(base)
    yield base
    svc._CACHE_LECTURA.clear()


# -- ventana y contadores ------------------------------------------------------
def test_listado_sin_filtros_oculta_los_slots_vacios(maquina):
    r = svc.listar_registros(MACHINE_ID)
    assert r["totales"] == {"mostrados": 12, "reales": 12, "total": 15}
    assert all(not reg["es_placeholder"] for reg in r["registros"])
    assert r["hash"]


def test_listado_con_placeholders_los_incluye(maquina):
    r = svc.listar_registros(MACHINE_ID, placeholders=True)
    assert r["totales"]["mostrados"] == 15
    assert sum(1 for reg in r["registros"] if reg["es_placeholder"]) == 3


def test_ventana_pagina_y_pos_es_la_posicion_en_la_lista_filtrada(maquina):
    primera = svc.listar_registros(MACHINE_ID, offset=0, limit=5)
    segunda = svc.listar_registros(MACHINE_ID, offset=5, limit=5)
    assert [reg["pos"] for reg in primera["registros"]] == [1, 2, 3, 4, 5]
    assert [reg["pos"] for reg in segunda["registros"]] == [6, 7, 8, 9, 10]
    # `index` es la posición REAL en el archivo: es con lo que se muta.
    assert segunda["registros"][0]["index"] == 5
    assert segunda["ventana"] == {"offset": 5, "limit": 5}
    # El total no cambia con la ventana: la barra de estado lo necesita entero.
    assert segunda["totales"]["mostrados"] == 12


def test_limit_se_recorta_al_tope(maquina):
    r = svc.listar_registros(MACHINE_ID, limit=99999)
    assert r["ventana"]["limit"] == svc.LIMITE_MAXIMO


# -- búsqueda y rangos ---------------------------------------------------------
def test_busqueda_mira_cualquier_campo_visible(maquina):
    por_codigo = svc.listar_registros(MACHINE_ID, q="C00007")
    assert por_codigo["totales"]["mostrados"] == 1
    assert por_codigo["registros"][0]["code"] == "C00007"

    por_nombre = svc.listar_registros(MACHINE_ID, q="pieza a0")
    assert por_nombre["totales"]["mostrados"] == 1

    por_numero = svc.listar_registros(MACHINE_ID, q="12")
    assert por_numero["totales"]["mostrados"] >= 1


def test_rango_numerico_filtra_por_los_dos_extremos(maquina):
    r = svc.listar_registros(MACHINE_ID, rangos_crudos=["grams:5:8"])
    assert sorted(reg["grams"] for reg in r["registros"]) == [5, 6, 7, 8]


def test_rango_con_un_solo_extremo(maquina):
    solo_min = svc.listar_registros(MACHINE_ID, rangos_crudos=["grams:10:"])
    assert all(reg["grams"] >= 10 for reg in solo_min["registros"])
    solo_max = svc.listar_registros(MACHINE_ID, rangos_crudos=["grams::3"])
    assert all(reg["grams"] <= 3 for reg in solo_max["registros"])


def test_rango_sin_limites_no_filtra(maquina):
    r = svc.listar_registros(MACHINE_ID, rangos_crudos=["grams::"])
    assert r["totales"]["mostrados"] == 12


def test_busqueda_y_rango_se_combinan(maquina):
    r = svc.listar_registros(MACHINE_ID, q="C0000", rangos_crudos=["grams:10:12"])
    assert all(reg["code"].startswith("C0000") and 10 <= reg["grams"] <= 12
               for reg in r["registros"])


@pytest.mark.parametrize("crudo", ["grams:1", "grams:a:b", "nombre:1:2", "nada:1:2"])
def test_rangos_invalidos_se_rechazan(maquina, crudo):
    with pytest.raises(svc.FiltroInvalido):
        svc.listar_registros(MACHINE_ID, rangos_crudos=[crudo])


# -- orden ---------------------------------------------------------------------
def test_orden_numerico_es_numerico_y_no_alfabetico(maquina):
    asc = svc.listar_registros(MACHINE_ID, orden="grams")
    valores = [reg["grams"] for reg in asc["registros"]]
    assert valores == sorted(valores)
    desc = svc.listar_registros(MACHINE_ID, orden="grams", descendente=True)
    assert [reg["grams"] for reg in desc["registros"]] == sorted(valores, reverse=True)


def test_orden_de_texto_ignora_mayusculas(maquina):
    r = svc.listar_registros(MACHINE_ID, orden="nombre")
    nombres = [reg["nombre"].lower() for reg in r["registros"]]
    assert nombres == sorted(nombres)


def test_orden_por_pos_vuelve_al_orden_del_archivo(maquina):
    r = svc.listar_registros(MACHINE_ID, orden="pos")
    indices = [reg["index"] for reg in r["registros"]]
    assert indices == sorted(indices)


def test_sin_orden_se_respeta_el_orden_del_archivo(maquina):
    r = svc.listar_registros(MACHINE_ID)
    assert [reg["index"] for reg in r["registros"]] == list(range(12))


def test_orden_por_columna_inexistente_se_rechaza(maquina):
    with pytest.raises(svc.FiltroInvalido):
        svc.listar_registros(MACHINE_ID, orden="no_existe")


def test_el_orden_se_aplica_antes_de_la_ventana(maquina):
    """Si la ventana se cortara antes de ordenar, la primera página traería
    los primeros registros del archivo en vez de los de menor gramaje."""
    r = svc.listar_registros(MACHINE_ID, orden="grams", limit=3)
    assert [reg["grams"] for reg in r["registros"]] == [1, 2, 3]


# -- índices filtrados ---------------------------------------------------------
def test_indices_filtrados_coinciden_con_el_listado(maquina):
    filtros = {"q": "C0000", "rangos_crudos": ["grams:5:12"], "orden": "grams"}
    listado = svc.listar_registros(MACHINE_ID, limit=svc.LIMITE_MAXIMO, **filtros)
    indices = svc.indices_filtrados(MACHINE_ID, **filtros)
    assert indices["indices"] == [reg["index"] for reg in listado["registros"]]


def test_indices_filtrados_devuelve_todo_el_conjunto_no_una_ventana(maquina):
    indices = svc.indices_filtrados(MACHINE_ID)
    assert len(indices["indices"]) == 12


# -- caché de lectura ----------------------------------------------------------
def test_la_cache_reusa_el_store_mientras_el_archivo_no_cambie(maquina):
    perfil = svc.cargar_perfil(MACHINE_ID)
    primero = svc._cargar_store_cacheado(perfil)
    segundo = svc._cargar_store_cacheado(perfil)
    assert primero is segundo


def test_la_cache_se_invalida_cuando_cambia_el_archivo(maquina):
    perfil = svc.cargar_perfil(MACHINE_ID)
    antes = svc._cargar_store_cacheado(perfil)
    _crear_maquina(maquina, n_reales=20, n_placeholders=3)
    despues = svc._cargar_store_cacheado(perfil)
    assert despues is not antes
    assert len(despues.records) == 23


def test_una_mutacion_no_toca_el_store_cacheado(maquina):
    """La ruta de escritura carga su propia copia: si compartiera el objeto
    con la caché, un alta se vería en las lecturas antes de guardarse."""
    perfil = svc.cargar_perfil(MACHINE_ID)
    cacheado = svc._cargar_store_cacheado(perfil)
    propio = svc._cargar_store(perfil)
    assert propio is not cacheado
    propio.add(propio.nuevo_registro({"code": "NUEVO", "grams": 1, "nombre": "x"}))
    assert len(cacheado.records) == 15


# -- carga (catálogo grande) ---------------------------------------------------
def test_catalogo_de_10000_registros_se_recorre_sin_reparsear(tmp_path, monkeypatch):
    """El catálogo más grande de planta supera los 5000 registros. Recorrer
    la tabla entera con ventanas de 200 tiene que leer el archivo UNA vez,
    no una por ventana."""
    base = str(tmp_path)
    monkeypatch.setattr(paths, "app_base_dir", lambda: base)
    svc._CACHE_LECTURA.clear()
    _crear_maquina(base, n_reales=10000, n_placeholders=0)

    lecturas = {"n": 0}
    original = DataStore.load

    def contando(path, profile):
        lecturas["n"] += 1
        return original(path, profile)

    monkeypatch.setattr(DataStore, "load", staticmethod(contando))

    comienzo = time.perf_counter()
    vistos = 0
    for offset in range(0, 10000, 200):
        r = svc.listar_registros(MACHINE_ID, offset=offset, limit=200)
        vistos += len(r["registros"])
    demora = time.perf_counter() - comienzo

    assert vistos == 10000
    assert lecturas["n"] == 1, "cada ventana volvió a parsear el archivo entero"
    # Cota amplia: no mide performance fina, protege contra una regresión
    # que vuelva cuadrático el recorrido de la tabla.
    assert demora < 10
    svc._CACHE_LECTURA.clear()
