"""Tests de la Fase 4 de PLAN_PARIDAD_UI.md: preview e integridad de
backups (B13), restaurar el original (B8), historial filtrable (B14) e
informes CSV de historial y diferencias (B9, B10), y exportar el archivo
actual u original (B7).

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
from app.services import maquinas_service as svc  # noqa: E402

MACHINE_ID = "historia"


def _perfil() -> dict:
    return {
        "id": MACHINE_ID,
        "nombre": "Máquina de prueba (historia)",
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
    _crear_maquina(base)
    yield base
    svc._CACHE_LECTURA.clear()


def _actual_path(base: str) -> str:
    return os.path.join(base, "datos", MACHINE_ID, "actual.csv")


def _leer(path: str) -> str:
    with open(path, encoding="utf-8") as f:
        return f.read()


# -- preview e integridad de backups (B13) --------------------------------------
def test_backup_preview_resume_perdidas_recuperos_y_cambios(maquina):
    # Un backup con el estado inicial (3 registros).
    svc.actualizar_registro(MACHINE_ID, 0, {"grams": 999})
    backup_nombre = consulta.listar_backups(MACHINE_ID)[0]["nombre"]

    # Cambios posteriores al backup: se borra C002, se agrega uno nuevo y se
    # modifica C001. Restaurar el backup revertiría todo eso.
    svc.eliminar_registro(MACHINE_ID, 2)
    svc.crear_registro(MACHINE_ID, {"code": "NUEVO", "grams": 1, "nombre": "z"})
    svc.actualizar_registro(MACHINE_ID, 1, {"grams": 500})

    preview = consulta.backup_preview(MACHINE_ID, backup_nombre)
    assert preview["integridad_ok"] is True
    assert "NUEVO" in preview["se_perderian"]
    assert "C002" in preview["se_recuperarian"]
    assert "C001" in preview["cambiarian"]


def test_backup_preview_backup_inexistente_da_404(maquina):
    with pytest.raises(FileNotFoundError):
        consulta.backup_preview(MACHINE_ID, "no-existe.csv")


def test_restaurar_backup_no_bloquea_por_hash_no_verificado(maquina):
    """El escritorio solo ADVIERTE si el hash no verifica, no bloquea la
    restauración (BackupsDialog._on_restaurar, app.py:2044): el operario
    decide después de ver el resumen de impacto."""
    svc.actualizar_registro(MACHINE_ID, 0, {"grams": 1})
    backup_nombre = consulta.listar_backups(MACHINE_ID)[0]["nombre"]
    ddir = os.path.join(maquina, "datos", MACHINE_ID, "backups")
    os.remove(os.path.join(ddir, f"{backup_nombre}.sha256"))

    preview = consulta.backup_preview(MACHINE_ID, backup_nombre)
    assert preview["integridad_ok"] is False

    r = consulta.restaurar_backup(MACHINE_ID, backup_nombre)
    assert "hash" in r


def test_restaurar_backup_respalda_el_estado_vigente_antes_de_pisarlo(maquina):
    svc.actualizar_registro(MACHINE_ID, 0, {"grams": 1})
    backup_nombre = consulta.listar_backups(MACHINE_ID)[0]["nombre"]
    n_backups_antes = len(consulta.listar_backups(MACHINE_ID))
    consulta.restaurar_backup(MACHINE_ID, backup_nombre)
    assert len(consulta.listar_backups(MACHINE_ID)) == n_backups_antes + 1


# -- restaurar el original (B8) --------------------------------------------------
def test_restaurar_original_descarta_todos_los_cambios(maquina):
    svc.crear_registro(MACHINE_ID, {"code": "NUEVO", "grams": 1, "nombre": "z"})
    svc.eliminar_registro(MACHINE_ID, 0)
    actual, original_path = _actual_path(maquina), os.path.join(
        maquina, "datos", MACHINE_ID, "original.csv")
    assert _leer(actual) != _leer(original_path)

    consulta.restaurar_original(MACHINE_ID)
    assert _leer(actual) == _leer(original_path)
    restantes = {x["code"] for x in svc.listar_registros(MACHINE_ID)["registros"]}
    assert restantes == {"C000", "C001", "C002"}


def test_restaurar_original_crea_un_backup_del_estado_vigente(maquina):
    svc.eliminar_registro(MACHINE_ID, 0)
    n_backups_antes = len(consulta.listar_backups(MACHINE_ID))
    consulta.restaurar_original(MACHINE_ID)
    assert len(consulta.listar_backups(MACHINE_ID)) == n_backups_antes + 1


def test_restaurar_original_registra_en_el_historial(maquina):
    consulta.restaurar_original(MACHINE_ID)
    eventos = consulta.listar_historial(MACHINE_ID)
    assert eventos[0]["accion"] == "restauracion"
    assert eventos[0]["clave"] == "original"


# -- historial filtrable (B14) ---------------------------------------------------
def test_historial_filtra_por_codigo(maquina):
    svc.actualizar_registro(MACHINE_ID, 0, {"grams": 1})  # C000
    svc.actualizar_registro(MACHINE_ID, 1, {"grams": 2})  # C001
    eventos = consulta.listar_historial(MACHINE_ID, codigo="c000")
    assert len(eventos) == 1
    assert eventos[0]["clave"] == "C000"


def test_historial_filtra_por_accion(maquina):
    svc.crear_registro(MACHINE_ID, {"code": "NUEVO", "grams": 1, "nombre": "z"})
    svc.actualizar_registro(MACHINE_ID, 0, {"grams": 5})
    altas = consulta.listar_historial(MACHINE_ID, accion="alta")
    assert len(altas) == 1
    assert altas[0]["clave"] == "NUEVO"


def test_historial_filtra_por_antiguedad_en_dias(maquina):
    svc.actualizar_registro(MACHINE_ID, 0, {"grams": 1})
    recientes = consulta.listar_historial(MACHINE_ID, desde_dias=7)
    assert len(recientes) == 1


def test_historial_mas_nuevo_primero(maquina):
    svc.actualizar_registro(MACHINE_ID, 0, {"grams": 1})
    svc.actualizar_registro(MACHINE_ID, 1, {"grams": 2})
    eventos = consulta.listar_historial(MACHINE_ID)
    assert eventos[0]["clave"] == "C001"
    assert eventos[1]["clave"] == "C000"


# -- informe CSV de historial (B9) -----------------------------------------------
def test_informe_csv_historial_incluye_encabezado_y_eventos(maquina):
    svc.actualizar_registro(MACHINE_ID, 0, {"grams": 1})
    filas = consulta.historial_informe_filas(MACHINE_ID)
    assert filas[0] == ["Fecha", "Usuario", "Acción", "Código", "Origen", "Versión",
                        "Valores anteriores", "Valores nuevos"]
    assert len(filas) == 2
    assert filas[1][2] == "Modificación"
    assert filas[1][3] == "C000"


def test_informe_csv_historial_respeta_el_filtro(maquina):
    svc.actualizar_registro(MACHINE_ID, 0, {"grams": 1})
    svc.actualizar_registro(MACHINE_ID, 1, {"grams": 2})
    filas = consulta.historial_informe_filas(MACHINE_ID, codigo="C000")
    assert len(filas) == 2  # encabezado + 1 evento


def test_informe_csv_historial_no_tiene_tope_de_limite(maquina):
    for _ in range(5):
        svc.actualizar_registro(MACHINE_ID, 0, {"grams": _})
    filas = consulta.historial_informe_filas(MACHINE_ID)
    assert len(filas) == 6  # encabezado + 5 eventos, sin el tope de 200 de la vista


# -- informe CSV de diferencias (B10) --------------------------------------------
def test_informe_csv_diferencias_incluye_todos_los_tipos(maquina):
    svc.crear_registro(MACHINE_ID, {"code": "NUEVO", "grams": 1, "nombre": "z"})
    svc.eliminar_registro(MACHINE_ID, 0)
    svc.actualizar_registro(MACHINE_ID, 0, {"grams": 999})  # ahora índice 0 es C001
    filas = consulta.diferencias_informe_filas(MACHINE_ID)
    codigos = {f[1] for f in filas[1:]}
    assert codigos == {"NUEVO", "C000", "C001"}


def test_informe_csv_diferencias_respeta_el_filtro_de_tipo(maquina):
    svc.crear_registro(MACHINE_ID, {"code": "NUEVO", "grams": 1, "nombre": "z"})
    svc.eliminar_registro(MACHINE_ID, 0)
    filas = consulta.diferencias_informe_filas(MACHINE_ID, tipos={"alta"})
    assert len(filas) == 2  # encabezado + el alta, sin la baja
    assert filas[1][0] == "alta"


# -- exportar el archivo actual u original (B7) ----------------------------------
def test_exportar_actual_devuelve_la_ruta_del_archivo_vigente(maquina):
    svc.actualizar_registro(MACHINE_ID, 0, {"grams": 1})
    ruta, nombre = consulta.ruta_exportar(MACHINE_ID, "actual")
    assert ruta == _actual_path(maquina)
    assert nombre == f"{MACHINE_ID}_actual.csv"


def test_exportar_original_devuelve_la_ruta_del_archivo_sin_cambios(maquina):
    ruta, nombre = consulta.ruta_exportar(MACHINE_ID, "original")
    assert ruta == os.path.join(maquina, "datos", MACHINE_ID, "original.csv")
    assert nombre == f"{MACHINE_ID}_original.csv"


def test_exportar_valor_invalido_de_cual_se_rechaza(maquina):
    with pytest.raises(ValueError):
        consulta.ruta_exportar(MACHINE_ID, "otra-cosa")
