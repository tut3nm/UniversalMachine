"""Tests de la Fase 3 de PLAN_PARIDAD_UI.md: chequeo de clave duplicada en
alta/edición (B0, gap encontrado al portar RecordDialog), edición en masa
(B1), baja en masa (B2), filtros guardados (B5) y salud completa con
slots_libres (B12).

Reusa el patrón de fixture de test_api_registros.py: una máquina sintética
aislada en tmp_path, con perfil y CSV propios.
"""

import json
import os
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "app", "core"))

import paths  # noqa: E402
from app.services import maquinas_service as svc  # noqa: E402

MACHINE_ID = "masiva"


def _perfil() -> dict:
    return {
        "id": MACHINE_ID,
        "nombre": "Máquina de prueba (masiva)",
        "descripcion": "",
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
             "min": 0, "max": 999, "default": 0},
            {"nombre_interno": "nombre", "rol": "parametro", "tipo": "texto",
             "titulo_ui": "Nombre", "columna": 2, "etiqueta": "Nombre"},
        ],
        "features": {
            "placeholder": {"patron": r"^_VACIO_\d+$", "generar": "_VACIO_{n}"},
        },
    }


def _crear_maquina(base: str, n_reales: int = 5, n_placeholders: int = 2) -> None:
    pdir = os.path.join(base, "profiles")
    os.makedirs(pdir, exist_ok=True)
    with open(os.path.join(pdir, f"maquina_{MACHINE_ID}.json"), "w",
              encoding="utf-8") as f:
        json.dump(_perfil(), f, ensure_ascii=False)

    ddir = os.path.join(base, "datos", MACHINE_ID)
    os.makedirs(ddir, exist_ok=True)
    filas = ["Codigo,Gramos,Nombre"]
    for i in range(n_reales):
        filas.append(f"C{i:03d},{i * 10},Pieza {i}")
    for j in range(1, n_placeholders + 1):
        filas.append(f"_VACIO_{j},0,")
    contenido = "\r\n".join(filas) + "\r\n"
    for nombre in ("actual.csv", "original.csv"):
        with open(os.path.join(ddir, nombre), "w", encoding="utf-8", newline="") as f:
            f.write(contenido)


@pytest.fixture
def maquina(tmp_path, monkeypatch):
    base = str(tmp_path)
    monkeypatch.setattr(paths, "app_base_dir", lambda: base)
    svc._CACHE_LECTURA.clear()
    _crear_maquina(base)
    yield base
    svc._CACHE_LECTURA.clear()


def _historial_path(base: str) -> str:
    return os.path.join(base, "datos", MACHINE_ID, "historial.jsonl")


def _n_eventos(base: str) -> int:
    ruta = _historial_path(base)
    if not os.path.exists(ruta):
        return 0
    with open(ruta, encoding="utf-8") as f:
        return sum(1 for _ in f)


def _n_backups(base: str) -> int:
    bdir = os.path.join(base, "datos", MACHINE_ID, "backups")
    if not os.path.isdir(bdir):
        return 0
    return sum(1 for n in os.listdir(bdir) if n.endswith(".csv"))


# -- clave duplicada en alta / edición ------------------------------------------
def test_alta_con_clave_duplicada_se_rechaza(maquina):
    with pytest.raises(svc.ClaveDuplicada) as exc:
        svc.crear_registro(MACHINE_ID, {"code": "C002", "grams": 5, "nombre": "x"})
    assert exc.value.posicion == 3  # C002 es el tercer registro (posición 1-based)
    # No se creó ningún backup: la validación corta ANTES de guardar.
    assert _n_backups(maquina) == 0


def test_edicion_con_clave_de_otro_registro_se_rechaza(maquina):
    with pytest.raises(svc.ClaveDuplicada):
        svc.actualizar_registro(MACHINE_ID, 0, {"code": "C002", "grams": 1, "nombre": "y"})


def test_edicion_que_conserva_su_propia_clave_no_se_confunde_con_duplicado(maquina):
    r = svc.actualizar_registro(MACHINE_ID, 0, {"code": "C000", "grams": 99, "nombre": "y"})
    assert r["registro"]["grams"] == 99


def test_edicion_sin_tocar_la_clave_no_dispara_el_chequeo(maquina):
    """`valores` puede no incluir el campo clave (solo se editó un
    parámetro): no debe compararse contra un None."""
    r = svc.actualizar_registro(MACHINE_ID, 1, {"grams": 55})
    assert r["registro"]["code"] == "C001"
    assert r["registro"]["grams"] == 55


def test_alta_con_clave_nueva_funciona_normalmente(maquina):
    r = svc.crear_registro(MACHINE_ID, {"code": "NUEVO", "grams": 1, "nombre": "z"})
    assert r["registro"]["code"] == "NUEVO"


# -- edición en masa -------------------------------------------------------------
def test_editar_en_masa_aplica_el_mismo_valor_a_todos(maquina):
    r = svc.editar_en_masa(MACHINE_ID, [0, 1, 2], "grams", "500")
    assert r["modificados"] == 3
    listado = svc.listar_registros(MACHINE_ID)["registros"]
    afectados = {x["index"]: x["grams"] for x in listado if x["index"] in (0, 1, 2)}
    assert afectados == {0: 500, 1: 500, 2: 500}


def test_editar_en_masa_es_un_solo_backup_pero_un_evento_por_registro(maquina):
    svc.editar_en_masa(MACHINE_ID, [0, 1, 2, 3], "grams", "1")
    assert _n_backups(maquina) == 1
    assert _n_eventos(maquina) == 4


def test_editar_en_masa_valida_rango_antes_de_tocar_nada(maquina):
    with pytest.raises(svc.ValoresInvalidos):
        svc.editar_en_masa(MACHINE_ID, [0, 1], "grams", "99999")
    # Ningún registro debe haber cambiado: la validación es previa.
    listado = svc.listar_registros(MACHINE_ID)["registros"]
    assert all(x["grams"] != 99999 for x in listado)
    assert _n_backups(maquina) == 0


def test_editar_en_masa_rechaza_el_campo_clave(maquina):
    with pytest.raises(svc.ValoresInvalidos):
        svc.editar_en_masa(MACHINE_ID, [0, 1], "code", "X")


def test_editar_en_masa_rechaza_indice_inexistente(maquina):
    with pytest.raises(IndexError):
        svc.editar_en_masa(MACHINE_ID, [0, 999], "grams", "1")


# -- baja en masa ------------------------------------------------------------
def test_eliminar_en_masa_borra_todos_los_indices(maquina):
    r = svc.eliminar_en_masa(MACHINE_ID, [1, 3])
    assert r["eliminados"] == 2
    restantes = {x["code"] for x in svc.listar_registros(MACHINE_ID)["registros"]}
    assert restantes == {"C000", "C002", "C004"}


def test_eliminar_en_masa_es_un_solo_backup_pero_un_evento_por_registro(maquina):
    svc.eliminar_en_masa(MACHINE_ID, [0, 2])
    assert _n_backups(maquina) == 1
    assert _n_eventos(maquina) == 2


def test_eliminar_en_masa_indices_duplicados_no_rompe_nada(maquina):
    """Un mismo índice repetido en la selección del cliente (p. ej. un doble
    clic) no debe intentar borrar dos veces la misma posición."""
    r = svc.eliminar_en_masa(MACHINE_ID, [2, 2])
    assert r["eliminados"] == 1
    assert len(svc.listar_registros(MACHINE_ID)["registros"]) == 4


def test_eliminar_en_masa_rechaza_indice_inexistente_sin_borrar_nada(maquina):
    with pytest.raises(IndexError):
        svc.eliminar_en_masa(MACHINE_ID, [0, 999])
    assert len(svc.listar_registros(MACHINE_ID)["registros"]) == 5


# -- salud con slots_libres ----------------------------------------------------
def test_salud_incluye_slots_libres(maquina):
    r = svc.salud_maquina(MACHINE_ID)
    assert r["slots_libres"] == 2  # los dos placeholders del fixture
    assert isinstance(r["hallazgos"], list)


def test_salud_slots_libres_es_cero_sin_placeholders(tmp_path, monkeypatch):
    base = str(tmp_path)
    monkeypatch.setattr(paths, "app_base_dir", lambda: base)
    svc._CACHE_LECTURA.clear()
    _crear_maquina(base, n_reales=3, n_placeholders=0)
    r = svc.salud_maquina(MACHINE_ID)
    assert r["slots_libres"] == 0
    svc._CACHE_LECTURA.clear()


# -- filtros guardados ----------------------------------------------------------
def test_filtros_guardados_arranca_vacio(maquina):
    assert svc.listar_filtros(MACHINE_ID) == []


def test_guardar_y_listar_un_filtro(maquina):
    presets = svc.guardar_filtro(MACHINE_ID, "Livianas", "pieza", ["grams:0:100"])
    assert len(presets) == 1
    assert presets[0]["nombre"] == "Livianas"
    assert presets[0]["busqueda"] == "pieza"
    assert presets[0]["rangos"] == {"grams": [0.0, 100.0]}
    assert svc.listar_filtros(MACHINE_ID) == presets


def test_guardar_con_el_mismo_nombre_reemplaza(maquina):
    svc.guardar_filtro(MACHINE_ID, "F1", "a", ["grams:0:10"])
    presets = svc.guardar_filtro(MACHINE_ID, "F1", "b", ["grams:5:20"])
    assert len(presets) == 1
    assert presets[0]["busqueda"] == "b"


def test_eliminar_filtro(maquina):
    svc.guardar_filtro(MACHINE_ID, "F1", "a", [])
    svc.guardar_filtro(MACHINE_ID, "F2", "b", [])
    restantes = svc.eliminar_filtro(MACHINE_ID, "F1")
    assert [p["nombre"] for p in restantes] == ["F2"]


def test_guardar_filtro_con_rango_invalido_se_rechaza(maquina):
    with pytest.raises(svc.FiltroInvalido):
        svc.guardar_filtro(MACHINE_ID, "F1", "a", ["nombre:1:2"])  # no numérico
