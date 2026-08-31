"""
test_metadata.py — Sidecar de metadatos, incluyendo manejo de corrupción
(Nivel 1.4) y limpieza de metadatos huérfanos (Nivel 2.5) del plan de
mejoras.
============================================================================
"""

import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "app", "core"))

from metadata import Sidecar  # noqa: E402


def test_carga_y_guarda_flags(tmp_path):
    path = tmp_path / "meta.json"
    sc = Sidecar.load(str(path))
    sc.set("A121538", "no_duplicado", True)
    sc.save()

    sc2 = Sidecar.load(str(path))
    assert sc2.get("A121538", "no_duplicado") is True
    assert sc2.keys_with("no_duplicado") == frozenset({"A121538"})
    assert sc2.recuperado_de_corrupcion is False


def test_archivo_inexistente_no_se_reporta_como_corrupto(tmp_path):
    path = tmp_path / "no_existe_todavia.json"
    sc = Sidecar.load(str(path))
    assert sc.recuperado_de_corrupcion is False, \
        "un sidecar que nunca existió no es 'corrupción', es el caso normal del primer arranque"


def test_json_corrupto_se_detecta_y_se_aisla(tmp_path):
    path = tmp_path / "meta.json"
    path.write_text("{ esto no es JSON válido", encoding="utf-8")

    sc = Sidecar.load(str(path))

    assert sc.recuperado_de_corrupcion is True
    assert sc.motivo_corrupcion is not None
    assert sc.keys_with("no_duplicado") == frozenset(), "arranca vacío, no crashea"

    # El archivo dañado NO desaparece: se renombra a un costado.
    assert not path.exists(), "el original corrupto ya no está en su ruta original"
    assert sc.ruta_respaldo_corrupto is not None
    assert os.path.exists(sc.ruta_respaldo_corrupto), \
        "el archivo corrupto se conserva en la ruta de respaldo, no se pierde"
    assert "esto no es JSON válido" in open(sc.ruta_respaldo_corrupto, encoding="utf-8").read()


def test_json_corrupto_sigue_funcionando_normalmente_despues(tmp_path):
    """Tras detectar la corrupción, el sidecar debe quedar 100% operativo:
    se pueden setear flags y guardar como si nada."""
    path = tmp_path / "meta.json"
    path.write_text("no es json", encoding="utf-8")

    sc = Sidecar.load(str(path))
    sc.set("B999", "no_duplicado", True)
    sc.save()

    sc2 = Sidecar.load(str(path))
    assert sc2.get("B999", "no_duplicado") is True
    assert sc2.recuperado_de_corrupcion is False, \
        "el archivo recién guardado es válido: la siguiente carga no debe reportar corrupción"


def test_json_con_estructura_inesperada_no_crashea(tmp_path):
    """Un JSON válido pero con una forma que no es la esperada (ej. una
    lista en vez de un objeto) no debe hacer explotar la carga."""
    path = tmp_path / "meta.json"
    path.write_text(json.dumps(["esto", "no", "es", "un", "dict"]), encoding="utf-8")

    # json.load() no falla acá (es JSON válido), pero .get("flags", {}) sobre
    # una lista lanzaría AttributeError si no se maneja. Documentamos el
    # comportamiento esperado: no debe propagar la excepción sin control.
    try:
        sc = Sidecar.load(str(path))
        assert sc.keys_with("no_duplicado") == frozenset()
    except AttributeError:
        raise AssertionError(
            "Sidecar.load() no debe crashear con AttributeError ante JSON de forma "
            "inesperada (lista en vez de dict) — debe tratarse como corrupción.")


# -- Limpieza de metadatos huérfanos (Nivel 2.5) ------------------------------

def test_save_sin_claves_validas_no_limpia_nada(tmp_path):
    """Comportamiento de siempre (sin pasar claves_validas): no se descarta
    ninguna clave por 'huérfana', solo se compactan flags todos en False."""
    path = tmp_path / "meta.json"
    sc = Sidecar.load(str(path))
    sc.set("BORRADO_HACE_TIEMPO", "no_duplicado", True)
    limpiadas = sc.save()
    assert limpiadas == 0

    sc2 = Sidecar.load(str(path))
    assert sc2.get("BORRADO_HACE_TIEMPO", "no_duplicado") is True


def test_save_con_claves_validas_descarta_huerfanas(tmp_path):
    path = tmp_path / "meta.json"
    sc = Sidecar.load(str(path))
    sc.set("A1", "no_duplicado", True)
    sc.set("BORRADO_HACE_TIEMPO", "no_duplicado", True)
    sc.save()  # sin limpiar todavía

    limpiadas = sc.save(claves_validas={"A1"})  # "BORRADO_HACE_TIEMPO" ya no existe
    assert limpiadas == 1

    sc2 = Sidecar.load(str(path))
    assert sc2.get("A1", "no_duplicado") is True
    assert sc2.get("BORRADO_HACE_TIEMPO", "no_duplicado") is False
    assert sc2.keys_with("no_duplicado") == frozenset({"A1"})


def test_save_con_claves_validas_y_sin_huerfanas_devuelve_cero(tmp_path):
    path = tmp_path / "meta.json"
    sc = Sidecar.load(str(path))
    sc.set("A1", "no_duplicado", True)
    limpiadas = sc.save(claves_validas={"A1", "A2"})
    assert limpiadas == 0
    assert sc.get("A1", "no_duplicado") is True


def test_save_limpieza_se_refleja_en_memoria_inmediatamente(tmp_path):
    """Tras save(claves_validas=...), el propio objeto Sidecar (sin
    recargar desde disco) ya debe reflejar la limpieza."""
    path = tmp_path / "meta.json"
    sc = Sidecar.load(str(path))
    sc.set("VIEJO", "no_duplicado", True)
    sc.save(claves_validas=set())  # ninguna clave vigente: se limpia todo
    assert sc.keys_with("no_duplicado") == frozenset()
