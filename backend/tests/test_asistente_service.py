import json
from pathlib import Path

import pytest

from app.ai import llm
from app.services import asistente_service as svc

REPO_ROOT = Path(__file__).resolve().parents[2]
LISTADO_PATH = REPO_ROOT / "docs" / "Recetas_Andon.txt"


def _stub(respuestas: list[str]):
    respuestas = list(respuestas)

    def ejecutar(system, user, grammar=None, max_tokens=768):
        return llm.LlmResult(True, respuestas.pop(0))

    return ejecutar


def test_interpretar_sin_listado_pantalla_gruesa_no_recetas():
    stub = _stub(['{"operacion": "tabular_mediciones"}'])
    resumen = svc.interpretar("tabulame las mediciones", None, None, ejecutar_llm=stub)
    assert resumen["requiere_pantalla"] == "tabular_mediciones"
    assert resumen["programa"] == [{"op": "tabular_mediciones", "args": {}}]


def test_interpretar_desconocido():
    stub = _stub(['{"operacion": "desconocido"}'])
    resumen = svc.interpretar("cual es la capital de francia", None, None, ejecutar_llm=stub)
    assert resumen["desconocido"] is True
    assert "mensaje" in resumen


def test_interpretar_recetas_sin_listado_pide_listado():
    stub = _stub(['{"operacion": "generar_recetas_por_area"}'])
    resumen = svc.interpretar("generame las recetas por area", None, None, ejecutar_llm=stub)
    assert resumen.get("requiere_listado") is True


def test_interpretar_recetas_con_listado_devuelve_vista_previa():
    stub = _stub([
        '{"operacion": "generar_recetas_por_area"}',
        "[]",
    ])
    resumen = svc.interpretar(
        "generame las recetas por area de este listado",
        LISTADO_PATH.read_bytes(),
        LISTADO_PATH.name,
        ejecutar_llm=stub,
    )
    assert resumen["cantidad_archivos"] == 54
    assert resumen["advertencias"] == []
    assert resumen["programa"] == [{"op": "expandir_por_catalogo", "args": {}}]
    assert "area" in resumen["descripcion"].lower()
    # el listado usa HD, que tiene el defecto real documentado en el plan
    assert any(h["regla"] == "descripcion_inconsistente_entre_variantes" for h in resumen["hallazgos"])


def test_ejecutar_produce_zip_con_54_archivos_agrupados_por_area():
    import zipfile
    import io

    programa = [{"op": "expandir_por_catalogo", "args": {}}]
    zip_bytes, nombre_zip, resumen = svc.ejecutar(
        programa, LISTADO_PATH.read_bytes(), LISTADO_PATH.name, texto_usuario="prueba"
    )
    assert resumen["cantidad_archivos"] == 54
    assert nombre_zip.endswith("_asistente.zip")

    with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zf:
        nombres = zf.namelist()
    assert len(nombres) == 54
    assert any(n.startswith("HD/") for n in nombres)
    assert any(n.startswith("GPS2/") for n in nombres)


def test_ejecutar_programa_invalido_lanza_asistente_error():
    programa = [{"op": "operacion_inventada", "args": {}}]
    with pytest.raises(svc.AsistenteError):
        svc.ejecutar(programa, LISTADO_PATH.read_bytes(), LISTADO_PATH.name)


def test_ejecutar_programa_mal_formado_lanza_asistente_error():
    with pytest.raises(svc.AsistenteError):
        svc.ejecutar("no es una lista", LISTADO_PATH.read_bytes(), LISTADO_PATH.name)


def test_ejecutar_deja_rastro_en_el_log(tmp_path, monkeypatch):
    import paths
    from app.ai.dsl import log as dsl_log

    monkeypatch.setattr(paths, "app_base_dir", lambda: str(tmp_path))

    programa = [{"op": "expandir_por_catalogo", "args": {}}]
    svc.ejecutar(programa, LISTADO_PATH.read_bytes(), LISTADO_PATH.name, texto_usuario="prueba de log")

    eventos = dsl_log.leer_eventos()
    assert eventos
    ultimo = eventos[-1]
    assert ultimo["operacion"] == "generar_recetas_por_area"
    assert ultimo["cantidad_archivos"] == 54
    assert ultimo["texto_usuario"] == "prueba de log"
    assert ultimo["programa"] == programa
