"""Tests de src/panel_multi_maquina.py (Nivel 4.9: panel multi-máquina)."""

import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "src"))

import paths  # noqa: E402
from profile import Profile  # noqa: E402
import panel_multi_maquina  # noqa: E402


def _perfil(machine_id: str, con_duplicados: bool = False):
    """Sin 'columna' fija en 'gramos' — DataStore.load() resuelve la
    columna por ETIQUETA, así un encabezado que no trae 'Gramos' levanta
    ValueError de inmediato (usado por el test del archivo corrupto)."""
    features = {"duplicados": {"metodo": "ignorar_ceros"}} if con_duplicados else {}
    data = {
        "id": machine_id, "nombre": f"Máquina {machine_id}", "descripcion": "",
        "archivo_inicial": "",
        "archivo": {"extension": "csv", "delimitador": ",", "encoding": "utf-8",
                    "bom": False, "fin_de_linea": "LF", "orientacion": "filas"},
        "estructura": {"fila_encabezado": 0, "primera_fila_datos": 1},
        "campos": [
            {"nombre_interno": "code", "rol": "clave", "etiqueta": "Codigo",
             "tipo": "texto", "titulo_ui": "Código"},
            {"nombre_interno": "gramos", "rol": "parametro", "etiqueta": "Gramos",
             "tipo": "entero", "titulo_ui": "Gramos", "min": 0, "max": 100},
        ],
        "features": features,
    }
    return Profile.from_dict(data)


def test_maquina_sin_datos_todavia(tmp_path, monkeypatch):
    monkeypatch.setattr(paths, "app_base_dir", lambda: str(tmp_path))
    resumen = panel_multi_maquina.resumen_de_maquina(_perfil("m1"))
    assert resumen.error == "sin datos todavía"
    assert resumen.cantidad_registros is None


def test_maquina_con_datos_cuenta_registros(tmp_path, monkeypatch):
    monkeypatch.setattr(paths, "app_base_dir", lambda: str(tmp_path))
    d = paths.data_dir_for("m2")
    with open(os.path.join(d, "actual.csv"), "w", encoding="utf-8", newline="") as f:
        f.write("Codigo,Gramos\r\nA1,10\r\nA2,20\r\n")
    resumen = panel_multi_maquina.resumen_de_maquina(_perfil("m2"))
    assert resumen.error is None
    assert resumen.cantidad_registros == 2
    assert resumen.ultima_modificacion is not None


def test_maquina_con_valor_fuera_de_rango_cuenta_alerta(tmp_path, monkeypatch):
    monkeypatch.setattr(paths, "app_base_dir", lambda: str(tmp_path))
    d = paths.data_dir_for("m3")
    with open(os.path.join(d, "actual.csv"), "w", encoding="utf-8", newline="") as f:
        f.write("Codigo,Gramos\r\nA1,999\r\n")
    resumen = panel_multi_maquina.resumen_de_maquina(_perfil("m3"))
    assert resumen.alertas_salud == 1


def test_maquina_con_archivo_corrupto_reporta_error(tmp_path, monkeypatch):
    monkeypatch.setattr(paths, "app_base_dir", lambda: str(tmp_path))
    d = paths.data_dir_for("m4")
    with open(os.path.join(d, "actual.csv"), "w", encoding="utf-8", newline="") as f:
        f.write("Codigo,OtraColumna\r\nA1,x\r\n")  # falta la columna Gramos
    resumen = panel_multi_maquina.resumen_de_maquina(_perfil("m4"))
    assert resumen.error is not None
    assert resumen.cantidad_registros is None


def test_maquina_sin_feature_duplicados_no_cuenta_duplicados(tmp_path, monkeypatch):
    monkeypatch.setattr(paths, "app_base_dir", lambda: str(tmp_path))
    d = paths.data_dir_for("m5")
    with open(os.path.join(d, "actual.csv"), "w", encoding="utf-8", newline="") as f:
        f.write("Codigo,Gramos\r\nA100,10\r\nA001,20\r\n")
    resumen = panel_multi_maquina.resumen_de_maquina(_perfil("m5", con_duplicados=False))
    assert resumen.duplicados_pendientes == 0


def test_maquina_con_feature_duplicados_los_cuenta(tmp_path, monkeypatch):
    monkeypatch.setattr(paths, "app_base_dir", lambda: str(tmp_path))
    d = paths.data_dir_for("m6")
    with open(os.path.join(d, "actual.csv"), "w", encoding="utf-8", newline="") as f:
        f.write("Codigo,Gramos\r\nA100,10\r\nA001,20\r\n")
    resumen = panel_multi_maquina.resumen_de_maquina(_perfil("m6", con_duplicados=True))
    assert resumen.duplicados_pendientes == 2


def test_resumen_de_todas_una_maquina_rota_no_bloquea_las_demas(tmp_path, monkeypatch):
    monkeypatch.setattr(paths, "app_base_dir", lambda: str(tmp_path))
    d_ok = paths.data_dir_for("ok1")
    with open(os.path.join(d_ok, "actual.csv"), "w", encoding="utf-8", newline="") as f:
        f.write("Codigo,Gramos\r\nA1,10\r\n")
    d_rota = paths.data_dir_for("rota1")
    with open(os.path.join(d_rota, "actual.csv"), "w", encoding="utf-8", newline="") as f:
        f.write("Codigo,OtraColumna\r\nA1,x\r\n")

    resumenes = panel_multi_maquina.resumen_de_todas(
        [_perfil("ok1"), _perfil("rota1")])
    assert len(resumenes) == 2
    por_id = {r.id: r for r in resumenes}
    assert por_id["ok1"].error is None
    assert por_id["ok1"].cantidad_registros == 1
    assert por_id["rota1"].error is not None
