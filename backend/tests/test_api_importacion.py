"""Tests de la Fase 5 de PLAN_PARIDAD_UI.md: duplicados (B4) e importación
desde Excel/CSV (B6).

Reusa el patrón de fixture de test_api_masivo.py: una máquina sintética
aislada en tmp_path, con perfil y CSV propios.
"""

import os
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "app", "core"))

import json  # noqa: E402

import paths  # noqa: E402
from app.services import duplicados_service as dup_svc  # noqa: E402
from app.services import import_service as imp_svc  # noqa: E402
from app.services import maquinas_service as svc  # noqa: E402

MACHINE_ID = "importacion"


def _perfil() -> dict:
    return {
        "id": MACHINE_ID,
        "nombre": "Máquina de prueba (importación)",
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
        "features": {"duplicados": {"metodo": "ignorar_ceros"}},
    }


def _crear_maquina(base: str, codigos: list[str]) -> None:
    pdir = os.path.join(base, "profiles")
    os.makedirs(pdir, exist_ok=True)
    with open(os.path.join(pdir, f"maquina_{MACHINE_ID}.json"), "w",
              encoding="utf-8") as f:
        json.dump(_perfil(), f, ensure_ascii=False)

    ddir = os.path.join(base, "datos", MACHINE_ID)
    os.makedirs(ddir, exist_ok=True)
    filas = ["Codigo,Gramos,Nombre"]
    for i, code in enumerate(codigos):
        filas.append(f"{code},{i * 10},Pieza {i}")
    contenido = "\r\n".join(filas) + "\r\n"
    for nombre in ("actual.csv", "original.csv"):
        with open(os.path.join(ddir, nombre), "w", encoding="utf-8", newline="") as f:
            f.write(contenido)


@pytest.fixture
def maquina(tmp_path, monkeypatch):
    base = str(tmp_path)
    monkeypatch.setattr(paths, "app_base_dir", lambda: base)
    svc._CACHE_LECTURA.clear()
    _crear_maquina(base, ["C000", "C001", "C002", "C003", "C004"])
    yield base
    svc._CACHE_LECTURA.clear()
    imp_svc._SESIONES.clear()


def _historial_path(base: str) -> str:
    return os.path.join(base, "datos", MACHINE_ID, "historial.jsonl")


def _eventos(base: str) -> list[dict]:
    ruta = _historial_path(base)
    if not os.path.exists(ruta):
        return []
    with open(ruta, encoding="utf-8") as f:
        return [json.loads(linea) for linea in f if linea.strip()]


# -- duplicados (B4) --------------------------------------------------------
def test_listar_duplicados_agrupa_por_firma(maquina):
    # C000 (código real "C000") no colisiona con nada; agregamos un
    # registro cuyo código, sin ceros, coincide con otro ("C1" vs "C001").
    svc.crear_registro(MACHINE_ID, {"code": "C1", "grams": 1, "nombre": "x"})
    r = dup_svc.listar_duplicados(MACHINE_ID)
    grupos = r["grupos"]
    assert len(grupos) == 1
    codigos = {reg["code"] for reg in grupos[0]["registros"]}
    assert codigos == {"C001", "C1"}


def test_marcar_no_duplicado_lo_excluye_de_futuras_busquedas(maquina):
    svc.crear_registro(MACHINE_ID, {"code": "C1", "grams": 1, "nombre": "x"})
    assert len(dup_svc.listar_duplicados(MACHINE_ID)["grupos"]) == 1

    r = dup_svc.marcar_no_duplicado(MACHINE_ID, "C1")
    assert r["grupos"] == []
    # Persiste: una nueva consulta (con el sidecar releído de disco) también
    # lo excluye.
    assert dup_svc.listar_duplicados(MACHINE_ID)["grupos"] == []


def test_eliminar_duplicados_borra_y_deja_un_evento_por_registro(maquina):
    svc.crear_registro(MACHINE_ID, {"code": "C1", "grams": 1, "nombre": "x"})
    grupo = dup_svc.listar_duplicados(MACHINE_ID)["grupos"][0]
    indices = [reg["index"] for reg in grupo["registros"] if reg["code"] == "C1"]

    r = dup_svc.eliminar_duplicados(MACHINE_ID, indices)
    assert r["eliminados"] == 1
    restantes = {x["code"] for x in svc.listar_registros(MACHINE_ID)["registros"]}
    assert "C1" not in restantes
    eventos = _eventos(maquina)
    assert eventos[-1]["accion"] == "baja"
    assert eventos[-1]["clave"] == "C1"


def test_sin_config_de_duplicados_no_hay_grupos(tmp_path, monkeypatch):
    base = str(tmp_path)
    monkeypatch.setattr(paths, "app_base_dir", lambda: base)
    svc._CACHE_LECTURA.clear()
    perfil = _perfil()
    perfil["features"] = {}
    pdir = os.path.join(base, "profiles")
    os.makedirs(pdir, exist_ok=True)
    with open(os.path.join(pdir, f"maquina_{MACHINE_ID}.json"), "w", encoding="utf-8") as f:
        json.dump(perfil, f, ensure_ascii=False)
    ddir = os.path.join(base, "datos", MACHINE_ID)
    os.makedirs(ddir, exist_ok=True)
    for nombre in ("actual.csv", "original.csv"):
        with open(os.path.join(ddir, nombre), "w", encoding="utf-8", newline="") as f:
            f.write("Codigo,Gramos,Nombre\r\nC001,1,x\r\nC1,1,x\r\n")
    assert dup_svc.listar_duplicados(MACHINE_ID)["grupos"] == []
    svc._CACHE_LECTURA.clear()


# -- importación (B6) --------------------------------------------------------
def _csv_import(contenido: str) -> bytes:
    return contenido.encode("utf-8")


def test_iniciar_importacion_csv_devuelve_headers_y_preview(maquina):
    contenido = _csv_import(
        "Codigo,Gramos,Nombre\r\nC000,999,Actualizado\r\nNUEVO,5,Pieza nueva\r\n")
    r = imp_svc.iniciar(MACHINE_ID, "cambios.csv", contenido)
    assert r["hojas"] == ["CSV"]
    assert r["headers"] == ["Codigo", "Gramos", "Nombre"]
    assert r["sugerencia"]["code"] == "Codigo"
    assert len(r["preview"]) == 2


def test_iniciar_con_extension_no_soportada_se_rechaza(maquina):
    with pytest.raises(imp_svc.ImportacionError):
        imp_svc.iniciar(MACHINE_ID, "cambios.txt", b"nada")


def test_mapear_exige_la_columna_clave(maquina):
    contenido = _csv_import("Gramos,Nombre\r\n999,Actualizado\r\n")
    r = imp_svc.iniciar(MACHINE_ID, "cambios.csv", contenido)
    with pytest.raises(imp_svc.ImportacionError):
        imp_svc.mapear(r["import_id"], {"grams": "Gramos"})


def test_mapear_exige_al_menos_un_dato_ademas_de_la_clave(maquina):
    contenido = _csv_import("Codigo,Gramos\r\nC000,999\r\n")
    r = imp_svc.iniciar(MACHINE_ID, "cambios.csv", contenido)
    with pytest.raises(imp_svc.ImportacionError):
        imp_svc.mapear(r["import_id"], {"code": "Codigo"})


def test_mapear_rechaza_columnas_repetidas(maquina):
    contenido = _csv_import("Codigo,Gramos\r\nC000,999\r\n")
    r = imp_svc.iniciar(MACHINE_ID, "cambios.csv", contenido)
    with pytest.raises(imp_svc.ImportacionError):
        imp_svc.mapear(r["import_id"], {"code": "Codigo", "grams": "Codigo"})


def test_mapear_calcula_diffs_nuevos_y_obsoletos(maquina):
    contenido = _csv_import(
        "Codigo,Gramos,Nombre\r\n"
        "C000,999,Actualizado\r\n"   # difiere de lo que hay (0)
        "C001,10,Pieza 1\r\n"        # igual a lo que hay -> sin cambios
        "NUEVO,5,Pieza nueva\r\n"    # no está en el catálogo -> nuevo
        # C002, C003, C004 no aparecen -> obsoletos
    )
    r = imp_svc.iniciar(MACHINE_ID, "cambios.csv", contenido)
    resultado = imp_svc.mapear(
        r["import_id"], {"code": "Codigo", "grams": "Gramos", "nombre": "Nombre"})

    assert [d["code"] for d in resultado["diffs"]] == ["C000"]
    assert resultado["diffs"][0]["errores"] == []
    assert [d["code"] for d in resultado["nuevos"]] == ["NUEVO"]
    assert {d["code"] for d in resultado["obsoletos"]} == {"C002", "C003", "C004"}
    assert resultado["sin_cambios"] == 1


def test_mapear_detecta_valores_fuera_de_rango(maquina):
    contenido = _csv_import("Codigo,Gramos,Nombre\r\nC000,99999,x\r\n")
    r = imp_svc.iniciar(MACHINE_ID, "cambios.csv", contenido)
    resultado = imp_svc.mapear(r["import_id"], {"code": "Codigo", "grams": "Gramos"})
    assert len(resultado["diffs"]) == 1
    assert resultado["diffs"][0]["errores"] != []


def test_aplicar_hace_un_solo_backup_y_un_evento_por_registro(maquina):
    contenido = _csv_import(
        "Codigo,Gramos,Nombre\r\n"
        "C000,999,Actualizado\r\n"
        "NUEVO,5,Pieza nueva\r\n")
    r = imp_svc.iniciar(MACHINE_ID, "cambios.csv", contenido)
    resultado = imp_svc.mapear(
        r["import_id"], {"code": "Codigo", "grams": "Gramos", "nombre": "Nombre"})
    diffs_codes = [d["code"] for d in resultado["diffs"]]
    nuevos_codes = [d["code"] for d in resultado["nuevos"]]
    obsoletos_codes = [d["code"] for d in resultado["obsoletos"]]

    aplicado = imp_svc.aplicar(r["import_id"], diffs_codes, nuevos_codes, obsoletos_codes, None)
    assert aplicado["modificados"] == 1
    assert aplicado["nuevos"] == 1
    assert aplicado["eliminados"] == 4  # C001, C002, C003, C004: no aparecen en el Excel

    bdir = os.path.join(maquina, "datos", MACHINE_ID, "backups")
    assert sum(1 for n in os.listdir(bdir) if n.endswith(".csv")) == 1

    eventos = _eventos(maquina)
    assert len(eventos) == 6  # 1 modificación + 1 alta + 4 bajas
    assert all(e["origen"] == "importacion" for e in eventos)

    registros = svc.listar_registros(MACHINE_ID)["registros"]
    assert {x["code"] for x in registros} == {"C000", "NUEVO"}
    assert next(x for x in registros if x["code"] == "C000")["grams"] == 999


def test_aplicar_solo_lo_seleccionado(maquina):
    contenido = _csv_import(
        "Codigo,Gramos,Nombre\r\nC000,999,x\r\nNUEVO,5,y\r\n")
    r = imp_svc.iniciar(MACHINE_ID, "cambios.csv", contenido)
    resultado = imp_svc.mapear(r["import_id"], {"code": "Codigo", "grams": "Gramos"})
    diffs_codes = [d["code"] for d in resultado["diffs"]]

    # Solo se aplica la modificación; ni el nuevo código ni los obsoletos.
    aplicado = imp_svc.aplicar(r["import_id"], diffs_codes, [], [], None)
    assert aplicado["modificados"] == 1
    assert aplicado["nuevos"] == 0
    assert aplicado["eliminados"] == 0
    registros = {x["code"] for x in svc.listar_registros(MACHINE_ID)["registros"]}
    assert registros == {"C000", "C001", "C002", "C003", "C004"}


def test_aplicar_sin_nada_seleccionado_se_rechaza(maquina):
    contenido = _csv_import("Codigo,Gramos\r\nC000,999\r\n")
    r = imp_svc.iniciar(MACHINE_ID, "cambios.csv", contenido)
    imp_svc.mapear(r["import_id"], {"code": "Codigo", "grams": "Gramos"})
    with pytest.raises(imp_svc.ImportacionError):
        imp_svc.aplicar(r["import_id"], [], [], [], None)


def test_aplicar_respeta_el_hash_esperado(maquina):
    contenido = _csv_import("Codigo,Gramos\r\nC000,999\r\n")
    r = imp_svc.iniciar(MACHINE_ID, "cambios.csv", contenido)
    resultado = imp_svc.mapear(r["import_id"], {"code": "Codigo", "grams": "Gramos"})
    diffs_codes = [d["code"] for d in resultado["diffs"]]

    with pytest.raises(svc.ConflictoEdicionExterna):
        imp_svc.aplicar(r["import_id"], diffs_codes, [], [], "hash-viejo-incorrecto")


def test_aplicar_borra_la_sesion(maquina):
    contenido = _csv_import("Codigo,Gramos\r\nC000,999\r\n")
    r = imp_svc.iniciar(MACHINE_ID, "cambios.csv", contenido)
    resultado = imp_svc.mapear(r["import_id"], {"code": "Codigo", "grams": "Gramos"})
    diffs_codes = [d["code"] for d in resultado["diffs"]]
    imp_svc.aplicar(r["import_id"], diffs_codes, [], [], None)
    with pytest.raises(KeyError):
        imp_svc.mapear(r["import_id"], {"code": "Codigo"})


def test_mapeo_confirmado_se_recuerda_para_la_proxima_importacion(maquina):
    contenido = _csv_import("Cod,Gr\r\nC000,999\r\n")
    r = imp_svc.iniciar(MACHINE_ID, "cambios.csv", contenido)
    imp_svc.mapear(r["import_id"], {"code": "Cod", "grams": "Gr"})

    # Un archivo nuevo con las mismas columnas: la sugerencia usa el mapeo
    # recordado, aunque el nombre no coincida con el título del perfil.
    contenido2 = _csv_import("Cod,Gr\r\nC001,5\r\n")
    r2 = imp_svc.iniciar(MACHINE_ID, "cambios2.csv", contenido2)
    assert r2["sugerencia"]["code"] == "Cod"
    assert r2["sugerencia"]["grams"] == "Gr"
