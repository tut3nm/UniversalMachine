import paths
from app.ai.dsl import log as dsl_log


def test_registrar_y_leer_eventos(tmp_path, monkeypatch):
    monkeypatch.setattr(paths, "app_base_dir", lambda: str(tmp_path))

    dsl_log.registrar_ejecucion(
        operacion="generar_recetas_por_area",
        programa=[{"op": "expandir_por_catalogo", "args": {}}],
        cantidad_archivos=54,
        texto_usuario="generame las recetas",
    )
    dsl_log.registrar_ejecucion(
        operacion="generar_recetas_por_area",
        programa=[{"op": "expandir_por_catalogo", "args": {"solo_sufijos": ["15"]}}],
        cantidad_archivos=13,
    )

    eventos = dsl_log.leer_eventos()
    assert len(eventos) == 2
    assert eventos[0]["cantidad_archivos"] == 54
    assert eventos[0]["texto_usuario"] == "generame las recetas"
    assert eventos[1]["cantidad_archivos"] == 13
    assert eventos[1]["texto_usuario"] == ""
    assert "timestamp" in eventos[0] and "usuario" in eventos[0]


def test_leer_eventos_sin_log_previo_da_lista_vacia(tmp_path, monkeypatch):
    monkeypatch.setattr(paths, "app_base_dir", lambda: str(tmp_path))
    assert dsl_log.leer_eventos() == []


def test_linea_corrupta_no_rompe_la_lectura(tmp_path, monkeypatch):
    monkeypatch.setattr(paths, "app_base_dir", lambda: str(tmp_path))
    dsl_log.registrar_ejecucion("op", [], 1)
    path = dsl_log._path_log()
    with open(path, "a", encoding="utf-8") as f:
        f.write("esto no es json\n")
    eventos = dsl_log.leer_eventos()
    assert len(eventos) == 1
