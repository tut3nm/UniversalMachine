"""ID automático (clave sintética), limpieza de acentos y detección de
codificación del wizard.

El archivo de prueba imita un export de recetas de WinCC: Windows-1252,
orientación por columnas, filas de encabezado, una fila 1..N, una fila de
nombres con repetidos y ningún campo que identifique a cada registro.
"""

import csv
import io
import os
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "app", "core"))

import paths  # noqa: E402
import profile_builder as PB  # noqa: E402
from datastore import DataStore  # noqa: E402
from profile import Profile  # noqa: E402
from texto_limpio import quitar_acentos  # noqa: E402
from app.services import consulta_service  # noqa: E402
from app.services import maquinas_service as svc  # noqa: E402
from app.services import wizard_service as W  # noqa: E402

N = 8


def _csv_wincc() -> bytes:
    nombres = ["N45", "N45", "N36", "N36", "N45", "N30", "N30", "N45"]  # repetidos
    filas = [
        ["List separator=", "Decimal symbol=,"] + [""] * (N - 1),
        ["Modelos Amortiguador "] + [""] * N,
        ["LANGID_c0a"] + nombres,
        ["1"] + [str(i) for i in range(1, N + 1)],
        ["RVERSION"] + ["n36/pesadö", "N45", "N36", "N36", "N45", "N30", "N30", "Ø45"],
        ["RGIRO"] + ["90"] * N,
        ["RALTURA"] + [f"{300 + i % 3},0000" for i in range(N)],
    ]
    buf = io.StringIO()
    csv.writer(buf, delimiter=";", lineterminator="\r\n").writerows(filas)
    return buf.getvalue().encode("cp1252")


# -- limpieza de texto ----------------------------------------------------------
def test_quita_acentos_y_dieresis_y_deja_el_resto_igual():
    assert quitar_acentos("n36/pesadö") == "n36/pesado"
    assert quitar_acentos("ÁÉÍÓÚ áéíóú Ü ü") == "AEIOU aeiou U u"
    # mayúsculas/minúsculas, símbolos raros y la ñ/ç se dejan tal cual
    assert quitar_acentos("Año Ø45 90° µm Ça") == "Año Ø45 90° µm Ça"


# -- codificación ---------------------------------------------------------------
def test_detecta_codificaciones():
    assert PB.detectar_codificacion("pesadö".encode("cp1252")) == ("cp1252", False)
    assert PB.detectar_codificacion("pesadö".encode("utf-8")) == ("utf-8", False)
    assert PB.detectar_codificacion(b"\xef\xbb\xbfabc") == ("utf-8", True)
    assert PB.detectar_codificacion("abc".encode("utf-16")) == ("utf-16", False)
    assert PB.detectar_codificacion(b"abc") == ("utf-8", False)


# -- wizard + motor con ID automático ---------------------------------------------
@pytest.fixture
def base(tmp_path, monkeypatch):
    b = str(tmp_path)
    monkeypatch.setattr(paths, "app_base_dir", lambda: b)
    os.makedirs(os.path.join(b, "profiles"), exist_ok=True)
    svc._CACHE_LECTURA.clear()
    yield b
    svc._CACHE_LECTURA.clear()


def _alta(base: str) -> str:
    ini = W.iniciar_alta("Modelos.csv", _csv_wincc())
    assert ini["info"]["encoding"] == "cp1252"
    assert ini["celdas_limpiadas"] == 1  # el «ö»; la «Ø» no es un acento
    wid = ini["wizard_id"]
    clas = W.clasificar(wid, "columnas", 1)
    # ninguna fila identifica a los registros (la 1..N es un índice)
    assert clas["clave_sugerida"] is None
    filas = [{"idx": f["idx"], "incluir": f["etiqueta"] in ("RVERSION", "RALTURA"),
              "nombre": f["etiqueta"].lower(), "titulo": f["etiqueta"],
              "tipo": f["tipo_sugerido"], "formato": f["formato_sugerido"]}
             for f in clas["filas"]]
    W.construir_perfil(wid, "wincc", "WinCC", "", None, filas)
    val = W.validar(wid)
    assert val["ok"], val
    assert val["id_automatico"] and val["n_registros"] == N
    assert any("ID" in a for a in val["advertencias"])
    W.confirmar(wid)
    return "wincc"


def test_alta_sin_clave_arma_perfil_con_id_automatico(base):
    mid = _alta(base)
    perfil = Profile.load(os.path.join(base, "profiles", f"maquina_{mid}.json"))
    assert perfil.id_auto and perfil.limpieza_acentos
    assert perfil.encoding == "cp1252"
    # encabezados anteriores a los datos quedan como filas fijas
    assert [f["fila"] for f in perfil.filas_fijas] == [0, 1]
    assert perfil.fila_indice["fila"] == 3
    clave = perfil.campo_clave()
    assert clave.sintetica and clave.nombre_interno == "id"


def test_ids_estables_al_borrar_agregar_y_recargar(base):
    mid = _alta(base)
    r = svc.listar_registros(mid)
    assert [x["id"] for x in r["registros"]] == list(range(1, N + 1))
    # el texto se muestra limpio
    assert r["registros"][0]["rversion"] == "n36/pesado"

    svc.eliminar_registro(mid, 2)  # borra el ID 3
    nuevo = svc.crear_registro(mid, {"rversion": "N99", "raltura": 310})
    assert nuevo["registro"]["id"] == N + 1  # nunca se reutiliza un ID

    svc._CACHE_LECTURA.clear()
    ids = [x["id"] for x in svc.listar_registros(mid)["registros"]]
    assert ids == [1, 2, 4, 5, 6, 7, 8, 9]  # los demás no se renumeraron

    # editar no puede cambiar el ID
    svc.actualizar_registro(mid, 0, {"id": 99, "rversion": "X1"})
    assert svc.listar_registros(mid)["registros"][0]["id"] == 1


def test_actual_guarda_ids_y_la_exportacion_no(base):
    mid = _alta(base)
    svc.eliminar_registro(mid, 0)
    actual = os.path.join(base, "datos", mid, "actual.csv")
    filas = list(csv.reader(open(actual, encoding="cp1252", newline=""), delimiter=";"))
    id_row = [f for f in filas if f and f[0] == "__ID_AUTO__"]
    assert len(id_row) == 1 and id_row[0][1:] == [str(i) for i in range(2, N + 1)]

    ruta, nombre = consulta_service.ruta_exportar(mid, "actual")
    exportado = open(ruta, "rb").read()
    assert b"__ID_AUTO__" not in exportado
    assert b"\xf6" not in exportado  # sin «ö» en cp1252
    assert b"\xd8" in exportado      # la «Ø» se conserva
    filas_exp = list(csv.reader(io.StringIO(exportado.decode("cp1252")), delimiter=";"))
    assert all(len(f) == N for f in filas_exp), "ancho consistente (N-1 datos + etiqueta)"
    # la fila 1..N se renumera sola al borrar un registro
    assert filas_exp[3] == ["1"] + [str(i) for i in range(1, N)]


def test_deshacer_baja_devuelve_el_mismo_id(base):
    mid = _alta(base)
    svc.eliminar_registro(mid, 4)  # ID 5
    svc.deshacer(mid)
    ids = sorted(x["id"] for x in svc.listar_registros(mid)["registros"])
    assert ids == list(range(1, N + 1))


def test_archivo_sin_acentos_ni_clave_sugiere_id_si_hay_repetidos():
    grid = [["a", "x", "x", "y"], ["b", "1", "1", "2"]]
    assert PB.suggest_clave_row(grid, 1, aproximada=False) is None
    assert PB.suggest_clave_row(grid, 1) is not None  # comportamiento anterior
