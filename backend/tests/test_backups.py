"""
test_backups.py — Nivel 2.1 del plan de mejoras.
============================================================================
"""

import os
import sys
from datetime import datetime, timedelta

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "app", "core"))

import backups  # noqa: E402
from profile import Profile  # noqa: E402
from datastore import DataStore  # noqa: E402


def _perfil():
    data = {
        "id": "synth", "nombre": "Sintético", "descripcion": "",
        "archivo": {"extension": "csv", "delimitador": ",", "encoding": "utf-8",
                    "bom": False, "fin_de_linea": "CRLF", "orientacion": "columnas"},
        "estructura": {"columna_etiquetas": 0, "primera_columna_datos": 1,
                       "filas_fijas": [], "fila_indice": None},
        "campos": [
            {"nombre_interno": "code", "rol": "clave", "fila": 0,
             "etiqueta": "Codigo", "tipo": "texto", "titulo_ui": "Código"},
            {"nombre_interno": "color", "rol": "parametro", "fila": 1,
             "etiqueta": "Color", "tipo": "entero", "titulo_ui": "Color"},
        ],
    }
    return Profile.from_dict(data)


# -- crear_backup / listar_backups --------------------------------------------

def test_crear_backup_sin_actual_previo_devuelve_none(tmp_path):
    path_actual = tmp_path / "actual.csv"  # no existe todavía
    assert backups.crear_backup(str(tmp_path), str(path_actual), "csv") is None
    assert backups.listar_backups(str(tmp_path)) == []


def test_crear_backup_copia_el_contenido_vigente(tmp_path):
    path_actual = tmp_path / "actual.csv"
    path_actual.write_text("Codigo,A1\r\nColor,1\r\n", encoding="utf-8", newline="")

    destino = backups.crear_backup(str(tmp_path), str(path_actual), "csv")
    assert destino is not None
    with open(destino, encoding="utf-8", newline="") as f:
        assert f.read() == "Codigo,A1\r\nColor,1\r\n"

    listado = backups.listar_backups(str(tmp_path))
    assert len(listado) == 1
    assert listado[0].ruta == destino


def test_backups_multiples_no_se_pisan_entre_si(tmp_path):
    path_actual = tmp_path / "actual.csv"
    path_actual.write_text("v1", encoding="utf-8")
    backups.crear_backup(str(tmp_path), str(path_actual), "csv")
    path_actual.write_text("v2", encoding="utf-8")
    backups.crear_backup(str(tmp_path), str(path_actual), "csv")
    path_actual.write_text("v3", encoding="utf-8")
    backups.crear_backup(str(tmp_path), str(path_actual), "csv")

    listado = backups.listar_backups(str(tmp_path))
    assert len(listado) == 3
    contenidos = set()
    for b in listado:
        with open(b.ruta, encoding="utf-8") as f:
            contenidos.add(f.read())
    assert contenidos == {"v1", "v2", "v3"}


def test_listar_backups_orden_mas_nuevo_primero(tmp_path):
    path_actual = tmp_path / "actual.csv"
    for v in ("v1", "v2", "v3"):
        path_actual.write_text(v, encoding="utf-8")
        backups.crear_backup(str(tmp_path), str(path_actual), "csv")
    listado = backups.listar_backups(str(tmp_path))
    timestamps = [b.timestamp for b in listado]
    assert timestamps == sorted(timestamps, reverse=True)


# -- verificar_integridad ------------------------------------------------------

def test_verificar_integridad_ok(tmp_path):
    path_actual = tmp_path / "actual.csv"
    path_actual.write_text("contenido", encoding="utf-8")
    backups.crear_backup(str(tmp_path), str(path_actual), "csv")
    b = backups.listar_backups(str(tmp_path))[0]
    assert backups.verificar_integridad(b) is True


def test_verificar_integridad_detecta_alteracion(tmp_path):
    path_actual = tmp_path / "actual.csv"
    path_actual.write_text("contenido", encoding="utf-8")
    backups.crear_backup(str(tmp_path), str(path_actual), "csv")
    b = backups.listar_backups(str(tmp_path))[0]
    with open(b.ruta, "w", encoding="utf-8") as f:
        f.write("contenido ALTERADO")
    assert backups.verificar_integridad(b) is False


def test_verificar_integridad_sin_sidecar_hash_no_es_confiable(tmp_path):
    path_actual = tmp_path / "actual.csv"
    path_actual.write_text("contenido", encoding="utf-8")
    backups.crear_backup(str(tmp_path), str(path_actual), "csv")
    b = backups.listar_backups(str(tmp_path))[0]
    os.remove(b.ruta_hash)
    assert backups.verificar_integridad(b) is False


# -- restaurar_backup -----------------------------------------------------------

def test_restaurar_backup_sobrescribe_actual(tmp_path):
    path_actual = tmp_path / "actual.csv"
    path_actual.write_text("version vieja", encoding="utf-8")
    backups.crear_backup(str(tmp_path), str(path_actual), "csv")
    b = backups.listar_backups(str(tmp_path))[0]

    path_actual.write_text("version nueva, editada despues del backup", encoding="utf-8")
    backups.restaurar_backup(b, str(path_actual))
    assert path_actual.read_text(encoding="utf-8") == "version vieja"


# -- purgar_backups (política de retención) -----------------------------------

def _crear_backup_con_fecha(tmp_path, fecha: datetime, contenido: str = "x") -> None:
    carpeta = os.path.join(str(tmp_path), "backups")
    os.makedirs(carpeta, exist_ok=True)
    nombre = f"actual-{fecha:%Y%m%d-%H%M%S-%f}.csv"
    with open(os.path.join(carpeta, nombre), "w", encoding="utf-8") as f:
        f.write(contenido)
    with open(os.path.join(carpeta, nombre + ".sha256"), "w", encoding="utf-8") as f:
        import hashlib
        f.write(hashlib.sha256(contenido.encode("utf-8")).hexdigest())


def test_purgar_mantiene_todos_los_de_hoy(tmp_path):
    ahora = datetime(2026, 7, 28, 15, 0, 0)
    for hora in (8, 9, 10, 11, 12):
        _crear_backup_con_fecha(tmp_path, ahora.replace(hour=hora))
    eliminados = backups.purgar_backups(str(tmp_path), ahora=ahora)
    assert eliminados == 0
    assert len(backups.listar_backups(str(tmp_path))) == 5


def test_purgar_mantiene_uno_por_dia_dentro_de_30_dias(tmp_path):
    ahora = datetime(2026, 7, 28, 15, 0, 0)
    dia_viejo = ahora - timedelta(days=10)
    # 3 backups el mismo día (hace 10 días): debe sobrevivir solo el más nuevo de ese día.
    _crear_backup_con_fecha(tmp_path, dia_viejo.replace(hour=8))
    _crear_backup_con_fecha(tmp_path, dia_viejo.replace(hour=12))
    _crear_backup_con_fecha(tmp_path, dia_viejo.replace(hour=18))

    eliminados = backups.purgar_backups(str(tmp_path), ahora=ahora)
    assert eliminados == 2
    restantes = backups.listar_backups(str(tmp_path))
    assert len(restantes) == 1
    assert restantes[0].timestamp.hour == 18, "se conserva el más reciente del día"


def test_purgar_mantiene_uno_por_mes_entre_30_y_365_dias(tmp_path):
    ahora = datetime(2026, 7, 28, 15, 0, 0)
    hace_6_meses = ahora - timedelta(days=180)
    _crear_backup_con_fecha(tmp_path, hace_6_meses.replace(day=5))
    _crear_backup_con_fecha(tmp_path, hace_6_meses.replace(day=20))

    eliminados = backups.purgar_backups(str(tmp_path), ahora=ahora)
    assert eliminados == 1
    restantes = backups.listar_backups(str(tmp_path))
    assert len(restantes) == 1
    assert restantes[0].timestamp.day == 20, "se conserva el más reciente del mes"


def test_purgar_elimina_todo_lo_mas_viejo_de_un_ano(tmp_path):
    ahora = datetime(2026, 7, 28, 15, 0, 0)
    hace_2_anos = ahora - timedelta(days=800)
    _crear_backup_con_fecha(tmp_path, hace_2_anos)

    eliminados = backups.purgar_backups(str(tmp_path), ahora=ahora)
    assert eliminados == 1
    assert backups.listar_backups(str(tmp_path)) == []


def test_purgar_elimina_tambien_el_sidecar_hash(tmp_path):
    ahora = datetime(2026, 7, 28, 15, 0, 0)
    hace_2_anos = ahora - timedelta(days=800)
    _crear_backup_con_fecha(tmp_path, hace_2_anos)
    carpeta = os.path.join(str(tmp_path), "backups")
    archivos_antes = os.listdir(carpeta)
    assert len(archivos_antes) == 2  # el backup + su .sha256

    backups.purgar_backups(str(tmp_path), ahora=ahora)
    assert os.listdir(carpeta) == []


def test_purgar_sin_backups_no_falla(tmp_path):
    assert backups.purgar_backups(str(tmp_path)) == 0


# -- resumir_diferencias --------------------------------------------------------

def test_resumir_diferencias_detecta_perdidas_recuperos_y_cambios():
    prof = _perfil()
    actual = DataStore(prof, [])
    actual.add(actual.nuevo_registro({"code": "A1", "color": 1}))  # se perdería
    actual.add(actual.nuevo_registro({"code": "A2", "color": 2}))  # cambiaría
    actual.add(actual.nuevo_registro({"code": "A3", "color": 3}))  # sin cambios

    backup = DataStore(prof, [])
    backup.add(backup.nuevo_registro({"code": "A2", "color": 99}))  # valor distinto
    backup.add(backup.nuevo_registro({"code": "A3", "color": 3}))   # igual
    backup.add(backup.nuevo_registro({"code": "A4", "color": 4}))   # se recuperaría

    resumen = backups.resumir_diferencias(actual, backup)
    assert resumen["se_perderian"] == ["A1"]
    assert resumen["se_recuperarian"] == ["A4"]
    assert resumen["cambiarian"] == ["A2"]


def test_resumir_diferencias_sin_cambios():
    prof = _perfil()
    actual = DataStore(prof, [])
    actual.add(actual.nuevo_registro({"code": "A1", "color": 1}))
    backup = DataStore(prof, [])
    backup.add(backup.nuevo_registro({"code": "A1", "color": 1}))

    resumen = backups.resumir_diferencias(actual, backup)
    assert resumen == {"se_perderian": [], "se_recuperarian": [], "cambiarian": []}
