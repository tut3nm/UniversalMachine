"""
`content_disposition()` (app/routers/_http.py) es el helper compartido que
arma el header `Content-Disposition` de toda descarga: nombre ASCII de
respaldo + `filename*` en UTF-8 (RFC 5987), para que un nombre de archivo
con acentos, "€" o comillas no rompa el header ni quede truncado. Antes cada
router lo armaba a mano con `filename="{nombre}"` crudo; este archivo fija
el contrato del helper y confirma que los routers que lo necesitaban ya lo
usan, ejercitando el endpoint real con un nombre de archivo "dificil".
"""
from __future__ import annotations

import asyncio
import io
import json
from pathlib import Path
from urllib.parse import unquote

from fastapi import UploadFile

from app.routers import editor_recetas, plantillas_masivas, recetas_por_area
from app.routers._http import content_disposition
from app.routers.consulta import _csv_response

REPO_ROOT = Path(__file__).resolve().parents[2]
PLANTILLA_PATH = REPO_ROOT / "docs" / "Recetas" / "plantilla.txt"
LISTADO_PATH = REPO_ROOT / "docs" / "Recetas_Andon.txt"

# Nombre "dificil" para probar los routers de punta a punta: acentos, un
# caracter fuera de latin-1 (el en-dash "–") y comillas embebidas. Las
# comillas antes rompian a editor_recetas_service al escribir el archivo
# subido a un temp file en Windows (_guardar_temp usaba el nombre crudo
# como path) - arreglado sanitizando el nombre solo para el path en disco,
# sin tocar el nombre que se devuelve al caller / Content-Disposition.
NOMBRE_DIFICIL = 'Código – prueba "x".csv'

CSV_RECETA = (
    "List separator=,Decimal symbol=.\r\n"
    "Recipe_1\r\n"
    "LANGID_409,P1,P2,P3,P4,P5,P6\r\n"
    "3,1,2,3,4,5,6\r\n"
    "Temperatura,45,50,55,60,65,70\r\n"
    "Presion,1.5,2.2,2.7,3.1,3.6,4.4\r\n"
    "Dureza,10,20,30,40,50,60\r\n"
)


def _upload(contenido: bytes, nombre: str) -> UploadFile:
    return UploadFile(io.BytesIO(contenido), filename=nombre)


def _run(coro):
    return asyncio.run(coro)


def _partes(header: str) -> tuple[str, str]:
    """(nombre ASCII de `filename=`, nombre real de `filename*=UTF-8''...`)."""
    ascii_ = header.split('filename="', 1)[1].split('"', 1)[0]
    utf8 = unquote(header.split("filename*=UTF-8''", 1)[1])
    return ascii_, utf8


# -- el helper en si mismo -----------------------------------------------------


def test_nombre_ascii_simple_queda_igual_en_ambas_partes():
    header = content_disposition("receta.csv")
    ascii_, utf8 = _partes(header)
    assert ascii_ == "receta.csv"
    assert utf8 == "receta.csv"


def test_nombre_con_acentos_y_fuera_de_latin1_no_rompe_el_header():
    header = content_disposition(NOMBRE_DIFICIL)
    # el header entero tiene que poder codificarse en latin-1: es lo que
    # exige Starlette/ASGI para un header HTTP
    header.encode("latin-1")
    ascii_, utf8 = _partes(header)
    assert utf8 == NOMBRE_DIFICIL
    # el respaldo ASCII no tiene el "–" (en-dash, fuera de ASCII) ni la "ó"
    assert all(ord(c) < 128 for c in ascii_)


def test_nombre_con_comillas_no_corta_el_header_ascii():
    ascii_, _ = _partes(content_disposition('a "b" c.txt'))
    assert '"' not in ascii_


# -- los routers ya usan el helper (no un f-string crudo) ---------------------


def test_consulta_csv_response_usa_filename_estrella():
    respuesta = _csv_response([["a", "b"], ["1", "2"]], NOMBRE_DIFICIL)
    header = respuesta.headers["Content-Disposition"]
    assert "filename*=UTF-8''" in header
    _, utf8 = _partes(header)
    assert utf8 == NOMBRE_DIFICIL


def test_editor_recetas_exportar_nombre_dificil():
    respuesta = _run(editor_recetas.exportar(_upload(CSV_RECETA.encode(), NOMBRE_DIFICIL)))
    assert respuesta.status_code == 200
    header = respuesta.headers["Content-Disposition"]
    assert "filename*=UTF-8''" in header
    _, utf8 = _partes(header)
    assert utf8.startswith('Código – prueba "x" (editable)')


def test_plantillas_masivas_generar_nombre_dificil():
    respuesta = _run(plantillas_masivas.generar(
        _upload(PLANTILLA_PATH.read_bytes(), NOMBRE_DIFICIL),
        _upload(LISTADO_PATH.read_bytes(), LISTADO_PATH.name),
    ))
    assert respuesta.status_code == 200
    header = respuesta.headers["Content-Disposition"]
    assert "filename*=UTF-8''" in header
    _, utf8 = _partes(header)
    assert utf8 == 'Código – prueba "x".zip'


def test_recetas_por_area_generar_nombre_dificil():
    respuesta = _run(recetas_por_area.generar(_upload(LISTADO_PATH.read_bytes(), NOMBRE_DIFICIL)))
    assert respuesta.status_code == 200
    header = respuesta.headers["Content-Disposition"]
    assert "filename*=UTF-8''" in header
    _, utf8 = _partes(header)
    assert utf8 == 'Código – prueba "x"_recetas.zip'


def test_asistente_ejecutar_ya_usaba_el_mismo_helper():
    from app.routers import asistente

    programa = json.dumps([{"op": "expandir_por_catalogo", "args": {}}])
    respuesta = _run(asistente.ejecutar(
        pantalla="recetas_por_area",
        programa=programa,
        texto="",
        listado=_upload(LISTADO_PATH.read_bytes(), NOMBRE_DIFICIL),
        datos=None,
        plantilla=None,
    ))
    assert respuesta.status_code == 200
    assert "filename*=UTF-8''" in respuesta.headers["Content-Disposition"]
