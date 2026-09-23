"""Tests de la Fase 6 de PLAN_PARIDAD_UI.md: deshacer y rehacer (B3) y
eliminar máquina (B11).

Reusa el patrón de fixture de test_api_masivo.py: una máquina sintética
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
from app.services import consulta_service as consulta  # noqa: E402
from app.services import import_service as imp_svc  # noqa: E402
from app.services import maquinas_service as svc  # noqa: E402

MACHINE_ID = "deshacer"


def _perfil() -> dict:
    return {
        "id": MACHINE_ID,
        "nombre": "Máquina de prueba (deshacer)",
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
        "features": {},
    }


def _crear_maquina(base: str, n_reales: int = 3) -> None:
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
    contenido = "\r\n".join(filas) + "\r\n"
    for nombre in ("actual.csv", "original.csv"):
        with open(os.path.join(ddir, nombre), "w", encoding="utf-8", newline="") as f:
            f.write(contenido)


@pytest.fixture
def maquina(tmp_path, monkeypatch):
    base = str(tmp_path)
    monkeypatch.setattr(paths, "app_base_dir", lambda: base)
    svc._CACHE_LECTURA.clear()
    svc._PILAS_DESHACER.clear()
    svc._PILAS_REHACER.clear()
    _crear_maquina(base)
    yield base
    svc._CACHE_LECTURA.clear()
    svc._PILAS_DESHACER.clear()
    svc._PILAS_REHACER.clear()
    imp_svc._SESIONES.clear()


def _codigos() -> set[str]:
    return {x["code"] for x in svc.listar_registros(MACHINE_ID)["registros"]}


def _historial_path(base: str) -> str:
    return os.path.join(base, "datos", MACHINE_ID, "historial.jsonl")


def _eventos(base: str) -> list[dict]:
    ruta = _historial_path(base)
    if not os.path.exists(ruta):
        return []
    with open(ruta, encoding="utf-8") as f:
        return [json.loads(linea) for linea in f if linea.strip()]


# -- estado inicial y validaciones --------------------------------------------
def test_estado_deshacer_arranca_vacio(maquina):
    r = svc.estado_deshacer(MACHINE_ID)
    assert r == {"puede_deshacer": False, "puede_rehacer": False,
                "descripcion_deshacer": None, "descripcion_rehacer": None}


def test_deshacer_sin_nada_para_deshacer_falla(maquina):
    with pytest.raises(svc.SinNadaQueDeshacer):
        svc.deshacer(MACHINE_ID)


def test_rehacer_sin_nada_para_rehacer_falla(maquina):
    with pytest.raises(svc.SinNadaQueRehacer):
        svc.rehacer(MACHINE_ID)


# -- deshacer alta / edición / baja --------------------------------------------
def test_deshacer_un_alta_borra_el_registro(maquina):
    svc.crear_registro(MACHINE_ID, {"code": "NUEVO", "grams": 1, "nombre": "z"})
    assert "NUEVO" in _codigos()

    estado = svc.estado_deshacer(MACHINE_ID)
    assert estado["puede_deshacer"] is True
    assert "NUEVO" in estado["descripcion_deshacer"]

    svc.deshacer(MACHINE_ID)
    assert "NUEVO" not in _codigos()
    assert svc.estado_deshacer(MACHINE_ID)["puede_rehacer"] is True


def test_deshacer_una_edicion_restaura_el_valor_anterior(maquina):
    svc.actualizar_registro(MACHINE_ID, 0, {"grams": 500})
    assert svc.listar_registros(MACHINE_ID)["registros"][0]["grams"] == 500

    svc.deshacer(MACHINE_ID)
    assert svc.listar_registros(MACHINE_ID)["registros"][0]["grams"] == 0


def test_deshacer_una_baja_recupera_el_registro(maquina):
    svc.eliminar_registro(MACHINE_ID, 1)
    assert "C001" not in _codigos()

    svc.deshacer(MACHINE_ID)
    assert "C001" in _codigos()


# -- rehacer ------------------------------------------------------------------
def test_rehacer_vuelve_a_aplicar_lo_deshecho(maquina):
    svc.crear_registro(MACHINE_ID, {"code": "NUEVO", "grams": 1, "nombre": "z"})
    svc.deshacer(MACHINE_ID)
    assert "NUEVO" not in _codigos()

    svc.rehacer(MACHINE_ID)
    assert "NUEVO" in _codigos()
    assert svc.estado_deshacer(MACHINE_ID)["puede_deshacer"] is True


def test_una_mutacion_nueva_vacia_la_pila_de_rehacer(maquina):
    svc.crear_registro(MACHINE_ID, {"code": "NUEVO", "grams": 1, "nombre": "z"})
    svc.deshacer(MACHINE_ID)
    assert svc.estado_deshacer(MACHINE_ID)["puede_rehacer"] is True

    svc.crear_registro(MACHINE_ID, {"code": "OTRO", "grams": 1, "nombre": "y"})
    assert svc.estado_deshacer(MACHINE_ID)["puede_rehacer"] is False
    with pytest.raises(svc.SinNadaQueRehacer):
        svc.rehacer(MACHINE_ID)


# -- deshacer/rehacer registra en el historial ---------------------------------
def test_deshacer_registra_un_evento_con_origen_deshacer(maquina):
    svc.crear_registro(MACHINE_ID, {"code": "NUEVO", "grams": 1, "nombre": "z"})
    svc.deshacer(MACHINE_ID)
    eventos = _eventos(maquina)
    assert eventos[-1]["origen"] == "deshacer"
    assert eventos[-1]["accion"] == "baja"  # deshacer un alta es una baja
    assert eventos[-1]["clave"] == "NUEVO"


def test_rehacer_registra_un_evento_con_origen_rehacer(maquina):
    svc.eliminar_registro(MACHINE_ID, 0)
    svc.deshacer(MACHINE_ID)
    svc.rehacer(MACHINE_ID)
    eventos = _eventos(maquina)
    assert eventos[-1]["origen"] == "rehacer"
    assert eventos[-1]["accion"] == "baja"
    assert eventos[-1]["clave"] == "C000"


# -- una operación en masa se deshace como una sola unidad ---------------------
def test_deshacer_una_edicion_en_masa_revierte_todos_los_registros(maquina):
    svc.editar_en_masa(MACHINE_ID, [0, 1, 2], "grams", "999")
    assert all(x["grams"] == 999 for x in svc.listar_registros(MACHINE_ID)["registros"])

    svc.deshacer(MACHINE_ID)
    valores = {x["code"]: x["grams"] for x in svc.listar_registros(MACHINE_ID)["registros"]}
    assert valores == {"C000": 0, "C001": 10, "C002": 20}


def test_deshacer_una_importacion_revierte_todos_los_cambios_de_una(maquina):
    contenido = b"Codigo,Gramos,Nombre\r\nC000,999,x\r\nNUEVO,5,y\r\n"
    r = imp_svc.iniciar(MACHINE_ID, "cambios.csv", contenido)
    resultado = imp_svc.mapear(r["import_id"], {"code": "Codigo", "grams": "Gramos"})
    diffs_codes = [d["code"] for d in resultado["diffs"]]
    nuevos_codes = [d["code"] for d in resultado["nuevos"]]
    imp_svc.aplicar(r["import_id"], diffs_codes, nuevos_codes, [], None)
    assert "NUEVO" in _codigos()
    assert svc.listar_registros(MACHINE_ID)["registros"][0]["grams"] == 999

    svc.deshacer(MACHINE_ID)
    assert "NUEVO" not in _codigos()
    assert svc.listar_registros(MACHINE_ID)["registros"][0]["grams"] == 0


# -- límite de 50 comandos ------------------------------------------------------
def test_la_pila_de_deshacer_no_supera_el_limite(maquina):
    for i in range(55):
        svc.crear_registro(MACHINE_ID, {"code": f"N{i}", "grams": 1, "nombre": "z"})
    assert len(svc._PILAS_DESHACER[MACHINE_ID]) == 50


# -- restaurar backup u original vacía las pilas -------------------------------
def test_restaurar_original_vacia_las_pilas_de_deshacer(maquina):
    svc.crear_registro(MACHINE_ID, {"code": "NUEVO", "grams": 1, "nombre": "z"})
    assert svc.estado_deshacer(MACHINE_ID)["puede_deshacer"] is True

    consulta.restaurar_original(MACHINE_ID)
    assert svc.estado_deshacer(MACHINE_ID) == {
        "puede_deshacer": False, "puede_rehacer": False,
        "descripcion_deshacer": None, "descripcion_rehacer": None,
    }


def test_restaurar_backup_vacia_las_pilas_de_deshacer(maquina):
    svc.actualizar_registro(MACHINE_ID, 0, {"grams": 1})  # crea un backup
    backup_nombre = consulta.listar_backups(MACHINE_ID)[0]["nombre"]
    svc.actualizar_registro(MACHINE_ID, 0, {"grams": 2})
    assert svc.estado_deshacer(MACHINE_ID)["puede_deshacer"] is True

    consulta.restaurar_backup(MACHINE_ID, backup_nombre)
    assert svc.estado_deshacer(MACHINE_ID)["puede_deshacer"] is False


# -- marcar no duplicado no es deshacible (solo metadatos) ----------------------
def test_marcar_no_duplicado_no_empuja_a_la_pila(maquina):
    from app.services import duplicados_service as dup_svc
    dup_svc.marcar_no_duplicado(MACHINE_ID, "C000")
    assert svc.estado_deshacer(MACHINE_ID)["puede_deshacer"] is False


# -- eliminar máquina (B11) -----------------------------------------------------
def test_eliminar_maquina_borra_perfil_y_datos(maquina):
    perfil_path = os.path.join(maquina, "profiles", f"maquina_{MACHINE_ID}.json")
    data_dir = os.path.join(maquina, "datos", MACHINE_ID)
    assert os.path.exists(perfil_path)
    assert os.path.isdir(data_dir)

    r = svc.eliminar_maquina(MACHINE_ID, "Máquina de prueba (deshacer)")
    assert r == {"eliminada": True}
    assert not os.path.exists(perfil_path)
    assert not os.path.isdir(data_dir)


def test_eliminar_maquina_con_nombre_incorrecto_se_rechaza(maquina):
    with pytest.raises(svc.ConfirmacionInvalida):
        svc.eliminar_maquina(MACHINE_ID, "nombre equivocado")
    # No se borró nada.
    perfil_path = os.path.join(maquina, "profiles", f"maquina_{MACHINE_ID}.json")
    assert os.path.exists(perfil_path)


def test_eliminar_maquina_inexistente_da_404(maquina):
    with pytest.raises(svc.MaquinaNoEncontrada):
        svc.eliminar_maquina("no-existe", "cualquier cosa")


def test_eliminar_maquina_limpia_las_pilas_de_deshacer(maquina):
    svc.crear_registro(MACHINE_ID, {"code": "NUEVO", "grams": 1, "nombre": "z"})
    assert MACHINE_ID in svc._PILAS_DESHACER
    svc.eliminar_maquina(MACHINE_ID, "Máquina de prueba (deshacer)")
    assert MACHINE_ID not in svc._PILAS_DESHACER
