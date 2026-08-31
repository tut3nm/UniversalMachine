"""Tests de src/arranque.py (seed_or_migrate / migrate_legacy_232),
extraído de App._seed_or_migrate / App._migrate_legacy_232 en el Nivel 3.1
del plan de mejoras."""

import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "src"))

import paths  # noqa: E402
import arranque  # noqa: E402
from profile import Profile  # noqa: E402
from datastore import DataStore  # noqa: E402
from metadata import Sidecar  # noqa: E402


def _perfil(machine_id="synth", archivo_inicial=""):
    data = {
        "id": machine_id, "nombre": "Sintética", "descripcion": "",
        "archivo_inicial": archivo_inicial,
        "archivo": {"extension": "csv", "delimitador": ",", "encoding": "utf-8",
                    "bom": False, "fin_de_linea": "LF", "orientacion": "filas"},
        "estructura": {"fila_encabezado": 0, "primera_fila_datos": 1},
        "campos": [
            {"nombre_interno": "code", "rol": "clave", "columna": 0,
             "etiqueta": "Codigo", "tipo": "texto", "titulo_ui": "Código"},
            {"nombre_interno": "color", "rol": "parametro", "columna": 1,
             "etiqueta": "Color", "tipo": "entero", "titulo_ui": "Color",
             "min": 1, "max": 9, "default": 1},
        ],
    }
    return Profile.from_dict(data)


def test_seed_sin_archivo_inicial_crea_catalogo_vacio(tmp_path, monkeypatch):
    monkeypatch.setattr(paths, "app_base_dir", lambda: str(tmp_path))
    profile = _perfil()
    path_original = str(tmp_path / "original.csv")
    path_actual = str(tmp_path / "actual.csv")
    path_meta = str(tmp_path / "meta.json")

    arranque.seed_or_migrate(profile, path_original, path_actual, path_meta)

    assert os.path.exists(path_original)
    assert os.path.exists(path_actual)
    store = DataStore.load(path_actual, profile)
    assert store.records == []


def test_seed_con_archivo_inicial_copia_ambos_destinos(tmp_path, monkeypatch):
    monkeypatch.setattr(paths, "app_base_dir", lambda: str(tmp_path))
    monkeypatch.setattr(paths, "resource_path", lambda rel: str(tmp_path / rel))

    fuente = tmp_path / "semilla.csv"
    fuente.write_text("Codigo,Color\nA1,5\n", encoding="utf-8", newline="")

    profile = _perfil(archivo_inicial="semilla.csv")
    path_original = str(tmp_path / "original.csv")
    path_actual = str(tmp_path / "actual.csv")
    path_meta = str(tmp_path / "meta.json")

    arranque.seed_or_migrate(profile, path_original, path_actual, path_meta)

    assert open(path_original, encoding="utf-8").read() == "Codigo,Color\nA1,5\n"
    assert open(path_actual, encoding="utf-8").read() == "Codigo,Color\nA1,5\n"


def _perfil_columnas_232():
    """Formato transpuesto real de la 232: cada registro es una columna, el
    código vive en la fila 2 (como en el CSV legado real)."""
    data = {
        "id": "232", "nombre": "232", "descripcion": "", "archivo_inicial": "",
        "archivo": {"extension": "csv", "delimitador": ",", "encoding": "utf-8",
                    "bom": False, "fin_de_linea": "LF", "orientacion": "columnas"},
        "estructura": {"columna_etiquetas": 0, "primera_columna_datos": 1,
                       "filas_fijas": [], "fila_indice": None},
        "campos": [
            {"nombre_interno": "a", "rol": "parametro", "fila": 0,
             "etiqueta": "f0", "tipo": "texto", "titulo_ui": "A"},
            {"nombre_interno": "b", "rol": "parametro", "fila": 1,
             "etiqueta": "f1", "tipo": "texto", "titulo_ui": "B"},
            {"nombre_interno": "code", "rol": "clave", "fila": 2,
             "etiqueta": "Codigo", "tipo": "texto", "titulo_ui": "Código"},
        ],
    }
    return Profile.from_dict(data)


def test_migracion_legado_232_copia_datos_y_marcas_de_revisado(tmp_path, monkeypatch):
    monkeypatch.setattr(paths, "app_base_dir", lambda: str(tmp_path))
    legacy = tmp_path / "datos232"
    legacy.mkdir()
    # Formato legado real: fila 2 = códigos, fila 7 = marcas de "revisado
    # como no duplicado" bajo la etiqueta LEGACY_REVIEW_LABEL.
    filas = [
        ["f0", "x", "y"],
        ["f1", "x", "y"],
        ["Codigo", "A1", "B2"],
        ["f3"], ["f4"], ["f5"], ["f6"],
        [arranque.LEGACY_REVIEW_LABEL, "1", "0"],
    ]
    contenido = "\n".join(",".join(f) for f in filas) + "\n"
    (legacy / "actual.csv").write_text(contenido, encoding="utf-8-sig", newline="")
    (legacy / "original.csv").write_text(contenido, encoding="utf-8-sig", newline="")

    profile = _perfil_columnas_232()
    path_original = str(tmp_path / "original.csv")
    path_actual = str(tmp_path / "actual.csv")
    path_meta = str(tmp_path / "meta.json")

    arranque.seed_or_migrate(profile, path_original, path_actual, path_meta)

    assert os.path.exists(path_original)
    assert os.path.exists(path_actual)
    sc = Sidecar.load(path_meta)
    assert sc.get("A1", "no_duplicado") is True
    assert sc.get("B2", "no_duplicado") is not True
