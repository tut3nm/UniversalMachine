"""Tests de src/instancia.py (Nivel 4.4: instancia única por máquina)."""

import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "src"))

import pytest  # noqa: E402

import instancia  # noqa: E402


def test_adquirir_sin_lock_previo_lo_crea(tmp_path):
    instancia.adquirir(str(tmp_path))
    info = instancia.leer_lock(str(tmp_path))
    assert info is not None
    assert info["pid"] == os.getpid()


def test_adquirir_con_lock_propio_vivo_lanza_bloqueada(tmp_path, monkeypatch):
    monkeypatch.setattr(instancia, "_proceso_vivo", lambda pid: True)
    instancia.adquirir(str(tmp_path))
    with pytest.raises(instancia.InstanciaBloqueadaError) as exc_info:
        instancia.adquirir(str(tmp_path))
    assert exc_info.value.info["pid"] == os.getpid()


def test_adquirir_con_lock_huerfano_lo_limpia_y_toma(tmp_path, monkeypatch):
    # Todo el lock que se encuentre a partir de acá se trata como huérfano
    # (proceso muerto) — dos adquisiciones seguidas no deben lanzar nunca.
    monkeypatch.setattr(instancia, "_proceso_vivo", lambda pid: False)
    instancia.adquirir(str(tmp_path))
    instancia.adquirir(str(tmp_path))  # no debe lanzar: el lock previo era huérfano
    info = instancia.leer_lock(str(tmp_path))
    assert info["pid"] == os.getpid()


def test_liberar_borra_el_lock(tmp_path):
    instancia.adquirir(str(tmp_path))
    instancia.liberar(str(tmp_path))
    assert instancia.leer_lock(str(tmp_path)) is None


def test_liberar_sin_lock_no_falla(tmp_path):
    instancia.liberar(str(tmp_path))  # no debe lanzar


def test_leer_lock_inexistente_es_none(tmp_path):
    assert instancia.leer_lock(str(tmp_path)) is None


def test_leer_lock_corrupto_es_none(tmp_path):
    (tmp_path / instancia.LOCK_FILENAME).write_text("{no es json", encoding="utf-8")
    assert instancia.leer_lock(str(tmp_path)) is None


def test_proceso_vivo_pid_invalido_es_false():
    assert instancia._proceso_vivo(-1) is False
    assert instancia._proceso_vivo(0) is False
    assert instancia._proceso_vivo(None) is False


def test_proceso_vivo_pid_propio_es_true():
    assert instancia._proceso_vivo(os.getpid()) is True


def test_proceso_vivo_pid_inexistente_es_false():
    # PID improbablemente en uso (muy alto) — en Windows los PID rondan
    # cientos/miles/decenas de miles; 999_999_999 no debería existir nunca.
    assert instancia._proceso_vivo(999_999_999) is False
