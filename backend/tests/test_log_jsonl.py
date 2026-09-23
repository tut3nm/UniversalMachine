from app import _bootstrap  # noqa: F401  (side effect: agrega app/core/ a sys.path)

import paths
import log_jsonl


def test_registrar_y_leer_eventos(tmp_path, monkeypatch):
    monkeypatch.setattr(paths, "app_base_dir", lambda: str(tmp_path))

    log_jsonl.registrar("mi_origen", {"archivo": "x.csv", "cantidad": 3})
    log_jsonl.registrar("mi_origen", {"archivo": "y.csv", "cantidad": 1})

    eventos = log_jsonl.leer_eventos("mi_origen")
    assert len(eventos) == 2
    assert eventos[0]["archivo"] == "x.csv"
    assert eventos[0]["cantidad"] == 3
    assert "timestamp" in eventos[0] and "usuario" in eventos[0]


def test_origenes_distintos_no_se_mezclan(tmp_path, monkeypatch):
    monkeypatch.setattr(paths, "app_base_dir", lambda: str(tmp_path))
    log_jsonl.registrar("asistente", {"a": 1})
    log_jsonl.registrar("editor_recetas", {"b": 2})
    assert len(log_jsonl.leer_eventos("asistente")) == 1
    assert len(log_jsonl.leer_eventos("editor_recetas")) == 1


def test_leer_eventos_sin_log_previo_da_lista_vacia(tmp_path, monkeypatch):
    monkeypatch.setattr(paths, "app_base_dir", lambda: str(tmp_path))
    assert log_jsonl.leer_eventos("nunca_registrado") == []


def test_linea_corrupta_no_rompe_la_lectura(tmp_path, monkeypatch):
    monkeypatch.setattr(paths, "app_base_dir", lambda: str(tmp_path))
    log_jsonl.registrar("origen", {"x": 1})
    path = log_jsonl._path("origen")
    with open(path, "a", encoding="utf-8") as f:
        f.write("esto no es json\n")
    assert len(log_jsonl.leer_eventos("origen")) == 1
