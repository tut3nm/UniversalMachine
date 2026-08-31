"""Tests de src/deteccion_externa.py (Nivel 4.3)."""

import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "app", "core"))

from deteccion_externa import hash_archivo, fue_modificado_externamente  # noqa: E402


def test_hash_archivo_inexistente_es_none(tmp_path):
    assert hash_archivo(str(tmp_path / "no_existe.csv")) is None


def test_hash_archivo_estable_si_no_cambia(tmp_path):
    p = tmp_path / "a.csv"
    p.write_text("hola", encoding="utf-8")
    assert hash_archivo(str(p)) == hash_archivo(str(p))


def test_hash_archivo_cambia_con_el_contenido(tmp_path):
    p = tmp_path / "a.csv"
    p.write_text("hola", encoding="utf-8")
    h1 = hash_archivo(str(p))
    p.write_text("chau", encoding="utf-8")
    h2 = hash_archivo(str(p))
    assert h1 != h2


def test_sin_hash_conocido_no_reporta_modificacion(tmp_path):
    p = tmp_path / "a.csv"
    p.write_text("hola", encoding="utf-8")
    assert fue_modificado_externamente(str(p), None) is False


def test_hash_conocido_coincide_no_reporta_modificacion(tmp_path):
    p = tmp_path / "a.csv"
    p.write_text("hola", encoding="utf-8")
    h = hash_archivo(str(p))
    assert fue_modificado_externamente(str(p), h) is False


def test_archivo_cambiado_por_fuera_se_detecta(tmp_path):
    p = tmp_path / "a.csv"
    p.write_text("hola", encoding="utf-8")
    h = hash_archivo(str(p))
    p.write_text("otro contenido", encoding="utf-8")
    assert fue_modificado_externamente(str(p), h) is True


def test_archivo_borrado_por_fuera_se_detecta(tmp_path):
    p = tmp_path / "a.csv"
    p.write_text("hola", encoding="utf-8")
    h = hash_archivo(str(p))
    os.remove(p)
    assert fue_modificado_externamente(str(p), h) is True
