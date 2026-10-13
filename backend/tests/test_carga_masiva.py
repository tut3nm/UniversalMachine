"""Carga masiva de registros nuevos desde Excel (PLAN_CARGA_MASIVA.md).

Mismo patrón de fixture que test_api_importacion.py: máquina sintética aislada
en tmp_path. El perfil tiene la PK `code` (no sintética), así que la carga
tiene que usarla como clave.
"""

import os
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "app", "core"))

import json  # noqa: E402

import paths  # noqa: E402
from app.services import import_service as imp_svc  # noqa: E402
from app.services import maquinas_service as svc  # noqa: E402

MACHINE_ID = "carga"


def _perfil() -> dict:
    return {
        "id": MACHINE_ID,
        "nombre": "Máquina de prueba (carga)",
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
    }


def _crear_maquina(base: str) -> None:
    pdir = os.path.join(base, "profiles")
    os.makedirs(pdir, exist_ok=True)
    with open(os.path.join(pdir, f"maquina_{MACHINE_ID}.json"), "w",
              encoding="utf-8") as f:
        json.dump(_perfil(), f, ensure_ascii=False)

    ddir = os.path.join(base, "datos", MACHINE_ID)
    os.makedirs(ddir, exist_ok=True)
    filas = ["Codigo,Gramos,Nombre"]
    for i, code in enumerate(["C000", "C001", "C002"]):
        filas.append(f"{code},{i * 10},Pieza {i}")
    contenido = "\r\n".join(filas) + "\r\n"
    for nombre in ("actual.csv", "original.csv"):
        with open(os.path.join(ddir, nombre), "w", encoding="utf-8", newline="") as f:
            f.write(contenido)


def _csv(texto: str) -> bytes:
    return texto.encode("utf-8")


@pytest.fixture
def maquina(tmp_path, monkeypatch):
    base = str(tmp_path)
    monkeypatch.setattr(paths, "app_base_dir", lambda: base)
    svc._CACHE_LECTURA.clear()
    _crear_maquina(base)
    yield base
    svc._CACHE_LECTURA.clear()
    imp_svc._SESIONES.clear()


def _registros() -> dict[str, dict]:
    return {x["code"]: x for x in svc.listar_registros(MACHINE_ID)["registros"]}


def test_carga_clasifica_altas_y_modificaciones_por_clave(maquina):
    contenido = _csv(
        "Codigo,Gramos,Nombre\r\n"
        "C000,9,Pieza 0\r\n"      # existe: cambia Gramos
        "NUEVO,5,Pieza nueva\r\n"  # no existe: alta
    )
    r = imp_svc.iniciar(MACHINE_ID, "carga.csv", contenido)
    res = imp_svc.mapear_carga(r["import_id"], [{"campo": "code", "columna": "Codigo"}],
                               {"grams": "Gramos", "nombre": "Nombre"})
    assert [d["busqueda"] for d in res["diffs"]] == ["C000"]
    assert [a["busqueda"] for a in res["altas"]] == ["NUEVO"]
    assert res["conflictos"] == []


def test_carga_vacio_numerico_queda_en_cero_y_texto_en_null(maquina):
    contenido = _csv("Codigo,Gramos,Nombre\r\nNUEVO,,\r\n")
    r = imp_svc.iniciar(MACHINE_ID, "carga.csv", contenido)
    res = imp_svc.mapear_carga(r["import_id"], [{"campo": "code", "columna": "Codigo"}],
                               {"grams": "Gramos", "nombre": "Nombre"})
    nuevo = res["altas"][0]["new"]
    assert nuevo["grams"] == 0
    assert nuevo["nombre"] is None


def test_carga_vacio_en_registro_existente_pone_cero_y_null(maquina):
    # C001 tiene Gramos 10 y Nombre "Pieza 1": el Excel los trae vacíos.
    contenido = _csv("Codigo,Gramos,Nombre\r\nC001,,\r\n")
    r = imp_svc.iniciar(MACHINE_ID, "carga.csv", contenido)
    res = imp_svc.mapear_carga(r["import_id"], [{"campo": "code", "columna": "Codigo"}],
                               {"grams": "Gramos", "nombre": "Nombre"})
    d = res["diffs"][0]
    assert d["new"]["grams"] == 0
    assert d["new"]["nombre"] is None


def test_carga_con_dos_claves_exige_coincidir_ambas(maquina):
    # Clave compuesta code+nombre: C000+"Pieza 0" existe; C000+"Otra" no existe,
    # pero su código ya está en el sistema, así que es conflicto y no alta.
    contenido = _csv("Codigo,Gramos,Nombre\r\nC000,9,Pieza 0\r\nC000,7,Otra\r\n")
    r = imp_svc.iniciar(MACHINE_ID, "carga.csv", contenido)
    res = imp_svc.mapear_carga(
        r["import_id"],
        [{"campo": "code", "columna": "Codigo"}, {"campo": "nombre", "columna": "Nombre"}],
        {"grams": "Gramos"})
    assert [d["busqueda"] for d in res["diffs"]] == ["C000 · Pieza 0"]
    assert res["altas"] == []
    assert len(res["conflictos"]) == 1
    assert "ya existe" in res["conflictos"][0]["motivo"]


def test_carga_codigo_repetido_en_el_archivo_es_conflicto(maquina):
    contenido = _csv("Codigo,Gramos,Nombre\r\nNUEVO,1,a\r\nNUEVO,2,b\r\n")
    r = imp_svc.iniciar(MACHINE_ID, "carga.csv", contenido)
    res = imp_svc.mapear_carga(r["import_id"], [{"campo": "code", "columna": "Codigo"}],
                               {"grams": "Gramos"})
    assert res["altas"] == []
    assert res["conflictos"][0]["codigo"] == "NUEVO"


def test_carga_fila_sin_clave_se_cuenta_y_no_se_importa(maquina):
    contenido = _csv("Codigo,Gramos,Nombre\r\n,5,sin codigo\r\nNUEVO,5,ok\r\n")
    r = imp_svc.iniciar(MACHINE_ID, "carga.csv", contenido)
    res = imp_svc.mapear_carga(r["import_id"], [{"campo": "code", "columna": "Codigo"}],
                               {"grams": "Gramos"})
    assert res["filas_sin_clave"] == 1
    assert [a["busqueda"] for a in res["altas"]] == ["NUEVO"]


def test_carga_aplica_altas_y_modificaciones_con_un_solo_backup(maquina):
    contenido = _csv(
        "Codigo,Gramos,Nombre\r\n"
        "C000,9,Pieza 0\r\n"
        "NUEVO,5,Pieza nueva\r\n")
    r = imp_svc.iniciar(MACHINE_ID, "carga.csv", contenido)
    res = imp_svc.mapear_carga(r["import_id"], [{"campo": "code", "columna": "Codigo"}],
                               {"grams": "Gramos", "nombre": "Nombre"})
    diffs = [d["id"] for d in res["diffs"]]
    altas = [a["id"] for a in res["altas"]]

    aplicado = imp_svc.aplicar(r["import_id"], diffs, [], None, altas)
    assert aplicado["modificados"] == 1
    assert aplicado["altas"] == 1
    assert aplicado["eliminados"] == 0

    regs = _registros()
    assert regs["C000"]["grams"] == 9
    assert regs["NUEVO"]["grams"] == 5
    assert regs["NUEVO"]["nombre"] == "Pieza nueva"

    bdir = os.path.join(maquina, "datos", MACHINE_ID, "backups")
    assert sum(1 for n in os.listdir(bdir) if n.endswith(".csv")) == 1


def test_carga_solo_aplica_lo_seleccionado(maquina):
    contenido = _csv("Codigo,Gramos,Nombre\r\nNUEVO,5,a\r\nOTRO,6,b\r\n")
    r = imp_svc.iniciar(MACHINE_ID, "carga.csv", contenido)
    res = imp_svc.mapear_carga(r["import_id"], [{"campo": "code", "columna": "Codigo"}],
                               {"grams": "Gramos"})
    aplicado = imp_svc.aplicar(r["import_id"], [], [], None, ["NUEVO"])
    assert aplicado["altas"] == 1
    regs = _registros()
    assert "NUEVO" in regs and "OTRO" not in regs
    assert len(res["altas"]) == 2


def test_carga_rechaza_mas_de_dos_claves_y_claves_sin_pk_en_perfil_sin_id(maquina):
    r = imp_svc.iniciar(MACHINE_ID, "carga.csv", _csv("Codigo,Gramos,Nombre\r\nX,1,a\r\n"))
    with pytest.raises(imp_svc.ImportacionError):
        imp_svc.mapear_carga(r["import_id"], [], {"grams": "Gramos"})
    with pytest.raises(imp_svc.ImportacionError):
        imp_svc.mapear_carga(
            r["import_id"],
            [{"campo": "grams", "columna": "Gramos"}, {"campo": "nombre", "columna": "Nombre"},
             {"campo": "code", "columna": "Codigo"}],
            {})
    # El código del perfil (PK no sintética) tiene que ser una de las claves.
    with pytest.raises(imp_svc.ImportacionError):
        imp_svc.mapear_carga(r["import_id"], [{"campo": "nombre", "columna": "Nombre"}],
                             {"grams": "Gramos"})


def test_carga_rechaza_columna_repetida(maquina):
    r = imp_svc.iniciar(MACHINE_ID, "carga.csv", _csv("Codigo,Gramos,Nombre\r\nX,1,a\r\n"))
    with pytest.raises(imp_svc.ImportacionError):
        imp_svc.mapear_carga(r["import_id"], [{"campo": "code", "columna": "Codigo"}],
                             {"grams": "Codigo"})


def test_actualizacion_sigue_sin_crear_registros(maquina):
    # Regresión: la actualización no da de alta ni vacía celdas.
    r = imp_svc.iniciar(MACHINE_ID, "cambios.csv", _csv("Codigo,Gramos,Nombre\r\nNUEVO,5,x\r\n"))
    res = imp_svc.mapear(r["import_id"], {"campo": "code", "columna": "Codigo"}, {"grams": "Gramos"})
    assert res["altas"] == []
    assert res["sin_coincidencia"] == [{"codigo": "NUEVO"}]
