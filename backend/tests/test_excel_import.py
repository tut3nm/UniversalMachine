"""Tests de src/excel_import.py (Nivel 4.6: separador de miles, aviso de
redondeo, importación desde CSV)."""

import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "app", "core"))

import excel_import  # noqa: E402


# -- separador de miles -------------------------------------------------------
def test_formato_regional_punto_miles_coma_decimal():
    assert excel_import.normalize_decimal("1.234,56") == 1234.56


def test_formato_us_coma_miles_punto_decimal():
    assert excel_import.normalize_decimal("1,234.56") == 1234.56


def test_solo_coma_se_trata_como_decimal_sin_cambios():
    assert excel_import.normalize_decimal("12,5") == 12.5


def test_solo_punto_se_trata_como_decimal_sin_cambios():
    assert excel_import.normalize_decimal("12.5") == 12.5


def test_entero_con_miles_regional():
    assert excel_import.normalize_int("1.234,00") == 1234


def test_entero_con_miles_us():
    assert excel_import.normalize_int("1,234.00") == 1234


# -- aviso de redondeo ---------------------------------------------------------
def test_tuvo_decimales_float_no_entero():
    assert excel_import.tuvo_decimales(1.5) is True


def test_tuvo_decimales_float_entero_es_false():
    assert excel_import.tuvo_decimales(2.0) is False


def test_tuvo_decimales_int_es_false():
    assert excel_import.tuvo_decimales(5) is False


def test_tuvo_decimales_none_es_false():
    assert excel_import.tuvo_decimales(None) is False


def test_tuvo_decimales_texto_con_decimales():
    assert excel_import.tuvo_decimales("3,5") is True


def test_tuvo_decimales_texto_sin_decimales():
    assert excel_import.tuvo_decimales("7") is False


def test_tuvo_decimales_texto_no_numerico_es_false():
    assert excel_import.tuvo_decimales("abc") is False


# -- importación desde CSV ------------------------------------------------------
def test_abrir_csv_expone_misma_api_que_workbook(tmp_path):
    p = tmp_path / "datos.csv"
    p.write_text("Codigo,Gramos\nA1,10\nA2,20\n", encoding="utf-8-sig", newline="")
    wb = excel_import.abrir_csv(str(p))
    assert excel_import.sheet_names(wb) == ["CSV"]
    headers = excel_import.read_headers(wb, "CSV")
    assert headers == ["Codigo", "Gramos"]
    rows = excel_import.read_rows_generic(wb, "CSV", {"code": 0, "gramos": 1})
    assert rows == [{"code": "A1", "gramos": "10"}, {"code": "A2", "gramos": "20"}]
    wb.close()  # no debe lanzar


def test_es_csv_por_extension():
    assert excel_import.es_csv("archivo.csv") is True
    assert excel_import.es_csv("archivo.CSV") is True
    assert excel_import.es_csv("archivo.xlsx") is False


def test_abrir_archivo_importacion_elige_csv_por_extension(tmp_path):
    p = tmp_path / "datos.csv"
    p.write_text("Codigo\nA1\n", encoding="utf-8-sig", newline="")
    wb = excel_import.abrir_archivo_importacion(str(p))
    assert isinstance(wb, excel_import.WorkbookCSV)


def test_abrir_csv_con_delimitador_punto_y_coma(tmp_path):
    p = tmp_path / "datos.csv"
    p.write_text("Codigo;Gramos\nA1;10\n", encoding="utf-8-sig", newline="")
    wb = excel_import.abrir_csv(str(p), delimitador=";")
    assert excel_import.read_headers(wb, "CSV") == ["Codigo", "Gramos"]


# -- _strip_accents (Nivel 5: cobertura completa vía unicodedata) -------------
def test_strip_accents_cubre_vocales_con_tilde():
    assert excel_import._strip_accents("código") == "codigo"


def test_strip_accents_cubre_enie():
    assert excel_import._strip_accents("Ñandú") == "Nandu"


def test_strip_accents_cubre_dieresis_y_otros_diacriticos():
    assert excel_import._strip_accents("müller") == "muller"
    assert excel_import._strip_accents("à la carte") == "a la carte"
    assert excel_import._strip_accents("façade") == "facade"
