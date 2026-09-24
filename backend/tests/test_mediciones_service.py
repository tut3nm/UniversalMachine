from pathlib import Path

import openpyxl

from app.services import mediciones_service as svc

DOCS = Path(__file__).resolve().parents[2] / "docs"


def test_csv_con_tablas_usa_el_motor_de_tablas():
    contenido = (DOCS / "H1312" / "824902015333_021224_000.csv").read_bytes()
    r = svc.procesar("824902015333_021224_000.csv", contenido, None, None, use_ai=False)
    assert r["modo"] == "tablas"
    assert [t["titulo"] for t in r["tablas"]] == ["Tabla 1", "Auftragsdaten", "Messprogrammseite 1", "QSStat"]
    assert openpyxl.load_workbook(r["out_path"]).sheetnames == [t["titulo"] for t in r["tablas"]]


def test_csv_con_tablas_avisa_que_no_usa_anotaciones():
    contenido = (DOCS / "H1312" / "824902015333_021224_000.csv").read_bytes()
    r = svc.procesar("datos.csv", contenido, "anot.txt", b"notas", use_ai=False)
    assert any("anotaciones" in a for a in r["advertencias"])


def test_log_sin_separadores_sigue_por_el_motor_de_registros():
    nombre = "Prod. 481700012633_con anotaciones.txt"
    r = svc.procesar(nombre, (DOCS / nombre).read_bytes(), None, None, use_ai=False)
    assert r["modo"] == "registros"
    assert r["records"] == 3
