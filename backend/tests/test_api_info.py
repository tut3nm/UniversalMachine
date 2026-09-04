"""Tests de los datos que alimentan la barra de estado y el "Acerca de"
de la webapp (GET /api/info), y de los interruptores del perfil que la UI
usa para decidir qué botones existen (GET /api/maquinas/{id}).

Se llaman las funciones directamente en vez de levantar un cliente HTTP:
no agregan dependencias de test y lo que interesa verificar es el contrato
de datos, no el ruteo de FastAPI.
"""

import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "app", "core"))

from app.main import info  # noqa: E402
from app.services import maquinas_service as svc  # noqa: E402


def test_info_trae_version_y_carpeta_de_log():
    datos = info()
    assert datos["titulo"]
    assert datos["version"]
    assert datos["compilacion"]
    assert os.path.isdir(datos["log_dir"])


def _perfil_de_prueba(tmp_path, con_placeholder: bool, con_duplicados: bool) -> str:
    """Escribe un perfil mínimo en un profiles/ propio y devuelve su id."""
    import json

    features = {}
    if con_placeholder:
        features["placeholder"] = {"patron": r"^_VACIO_\d+$", "generar": "_VACIO_{n}"}
    if con_duplicados:
        features["duplicados"] = {"metodo": "ignorar_ceros", "campo": "code"}
    perfil = {
        "id": "pruebaui",
        "nombre": "Máquina de prueba",
        "descripcion": "solo para tests",
        "archivo_inicial": "",
        "archivo": {
            "extension": "csv",
            "delimitador": ";",
            "encoding": "utf-8",
            "bom": False,
            "fin_de_linea": "CRLF",
            "orientacion": "filas",
        },
        "estructura": {"fila_encabezado": 0, "primera_fila_datos": 1},
        "campos": [
            {"nombre_interno": "code", "rol": "clave", "tipo": "texto",
             "titulo_ui": "Código", "columna": 0, "etiqueta": "Codigo"},
            {"nombre_interno": "gramos", "rol": "parametro", "tipo": "entero",
             "titulo_ui": "Gramos", "columna": 1, "etiqueta": "Gramos",
             "min": 0, "max": 900},
        ],
        "features": features,
    }
    pdir = tmp_path / "profiles"
    pdir.mkdir(exist_ok=True)
    (pdir / "maquina_pruebaui.json").write_text(
        json.dumps(perfil, ensure_ascii=False), encoding="utf-8")
    return str(pdir)


def test_obtener_maquina_expone_los_interruptores_del_perfil(tmp_path, monkeypatch):
    import paths

    pdir = _perfil_de_prueba(tmp_path, con_placeholder=True, con_duplicados=True)
    monkeypatch.setattr(paths, "profiles_dir", lambda: pdir)

    datos = svc.obtener_maquina("pruebaui")
    assert datos["nombre"] == "Máquina de prueba"
    assert datos["extension"] == "csv"
    assert datos["orientacion"] == "filas"
    assert datos["tiene_placeholders"] is True
    assert datos["tiene_duplicados"] is True
    # La UI arma el diálogo de alta con esto: necesita tipo y rango.
    gramos = next(c for c in datos["campos"] if c["nombre_interno"] == "gramos")
    assert gramos["tipo"] == "entero"
    assert gramos["min"] == 0
    assert gramos["max"] == 900


def test_obtener_maquina_sin_features_apaga_los_interruptores(tmp_path, monkeypatch):
    import paths

    pdir = _perfil_de_prueba(tmp_path, con_placeholder=False, con_duplicados=False)
    monkeypatch.setattr(paths, "profiles_dir", lambda: pdir)

    datos = svc.obtener_maquina("pruebaui")
    assert datos["tiene_placeholders"] is False
    assert datos["tiene_duplicados"] is False
