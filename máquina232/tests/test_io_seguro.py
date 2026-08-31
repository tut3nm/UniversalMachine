"""
test_io_seguro.py — escritura atómica (Nivel 1.1 del plan de mejoras).
======================================================================
Verifica que escribir_atomico() nunca deje el archivo destino a medio
escribir: o se actualiza completo, o se queda exactamente como estaba antes.
"""

import os
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "src"))

import io_seguro  # noqa: E402


def test_escribe_contenido_nuevo(tmp_path):
    path = tmp_path / "archivo.csv"
    io_seguro.escribir_atomico(str(path), "hola\r\nmundo\r\n", encoding="utf-8")
    with open(path, "rb") as f:
        assert f.read() == b"hola\r\nmundo\r\n"


def test_sobreescribe_contenido_existente(tmp_path):
    path = tmp_path / "archivo.csv"
    path.write_text("version vieja", encoding="utf-8")
    io_seguro.escribir_atomico(str(path), "version nueva", encoding="utf-8")
    assert path.read_text(encoding="utf-8") == "version nueva"


def test_no_deja_archivos_temporales_tras_exito(tmp_path):
    path = tmp_path / "archivo.csv"
    io_seguro.escribir_atomico(str(path), "contenido", encoding="utf-8")
    restantes = [p.name for p in tmp_path.iterdir()]
    assert restantes == ["archivo.csv"], \
        f"no debe quedar ningún .tmp-* huérfano: {restantes}"


def test_respeta_encoding_utf8_sig(tmp_path):
    path = tmp_path / "con_bom.csv"
    io_seguro.escribir_atomico(str(path), "código,1\r\n", encoding="utf-8-sig")
    with open(path, "rb") as f:
        data = f.read()
    assert data.startswith(b"\xef\xbb\xbf"), "el BOM se escribe cuando se pide utf-8-sig"


def test_no_traduce_fin_de_linea(tmp_path):
    """newline="" (default) no debe convertir \\n sueltos a \\r\\n ni nada
    parecido: el contenido en memoria ya trae el fin de línea exacto que
    espera el perfil de la máquina."""
    path = tmp_path / "lf.csv"
    io_seguro.escribir_atomico(str(path), "a\nb\nc\n", encoding="utf-8")
    with open(path, "rb") as f:
        assert f.read() == b"a\nb\nc\n"


def test_fallo_a_mitad_de_escritura_no_corrompe_el_original(tmp_path, monkeypatch):
    """Simula un crash DESPUÉS de crear el temporal pero ANTES de completar
    el volcado a disco (fsync): el archivo original debe seguir intacto y no
    debe quedar ningún .tmp-* huérfano permanentemente bloqueando la carpeta."""
    path = tmp_path / "actual.csv"
    path.write_text("contenido original intacto", encoding="utf-8")

    def fsync_que_falla(fd):
        raise OSError("simulación de corte de energía a mitad de escritura")

    monkeypatch.setattr(os, "fsync", fsync_que_falla)

    with pytest.raises(OSError):
        io_seguro.escribir_atomico(str(path), "contenido nuevo que nunca debería quedar",
                                    encoding="utf-8")

    assert path.read_text(encoding="utf-8") == "contenido original intacto", \
        "el archivo original no se toca si la escritura falla antes del replace"
    restantes = [p.name for p in tmp_path.iterdir()]
    assert restantes == ["actual.csv"], \
        f"el .tmp-* se limpia aunque la escritura haya fallado: {restantes}"


def test_replace_reintenta_ante_permission_error_transitorio(tmp_path, monkeypatch):
    """Simula el escenario real observado en Windows: un antivirus/indexador
    tiene el archivo agarrado una fracción de segundo justo cuando se
    intenta reemplazarlo (PermissionError transitorio). Un reintento breve
    debe resolverlo sin que el llamador vea ningún error."""
    path = tmp_path / "actual.csv"
    path.write_text("original", encoding="utf-8")

    real_replace = os.replace
    intentos = {"n": 0}

    def replace_falla_una_vez(src, dst):
        intentos["n"] += 1
        if intentos["n"] == 1:
            raise PermissionError("simulación: archivo en uso por otro proceso")
        return real_replace(src, dst)

    monkeypatch.setattr(os, "replace", replace_falla_una_vez)
    io_seguro.escribir_atomico(str(path), "nuevo contenido", encoding="utf-8")

    assert path.read_text(encoding="utf-8") == "nuevo contenido"
    assert intentos["n"] == 2, "debió reintentar una vez tras el PermissionError transitorio"


def test_replace_propaga_si_el_permission_error_persiste(tmp_path, monkeypatch):
    path = tmp_path / "actual.csv"
    path.write_text("original", encoding="utf-8")

    def replace_siempre_falla(src, dst):
        raise PermissionError("simulación: archivo bloqueado permanentemente")

    monkeypatch.setattr(os, "replace", replace_siempre_falla)
    monkeypatch.setattr(io_seguro, "_ESPERA_ENTRE_REINTENTOS_SEG", 0.001)  # no ralentizar el test
    with pytest.raises(PermissionError):
        io_seguro.escribir_atomico(str(path), "nuevo contenido", encoding="utf-8")

    assert path.read_text(encoding="utf-8") == "original", \
        "si todos los reintentos fallan, el archivo original sigue intacto"


def test_fallo_en_replace_no_deja_temporal_huerfano(tmp_path, monkeypatch):
    path = tmp_path / "actual.csv"
    path.write_text("original", encoding="utf-8")

    real_replace = os.replace

    def replace_que_falla(src, dst):
        raise OSError("simulación de fallo de os.replace (p. ej. archivo en uso)")

    monkeypatch.setattr(os, "replace", replace_que_falla)
    with pytest.raises(OSError):
        io_seguro.escribir_atomico(str(path), "nuevo", encoding="utf-8")
    monkeypatch.setattr(os, "replace", real_replace)

    assert path.read_text(encoding="utf-8") == "original"
    restantes = [p.name for p in tmp_path.iterdir()]
    assert restantes == ["actual.csv"], f"no debe quedar temporal huérfano: {restantes}"


def test_crea_carpeta_destino_si_no_existe(tmp_path):
    path = tmp_path / "subcarpeta" / "nueva" / "archivo.csv"
    io_seguro.escribir_atomico(str(path), "contenido", encoding="utf-8")
    assert path.read_text(encoding="utf-8") == "contenido"


def test_escribir_bytes_atomico(tmp_path):
    path = tmp_path / "binario.csv"
    io_seguro.escribir_bytes_atomico(str(path), b"\xef\xbb\xbfabc\r\n")
    with open(path, "rb") as f:
        assert f.read() == b"\xef\xbb\xbfabc\r\n"


# -- verificar_contenido() ----------------------------------------------------

def test_verificar_contenido_coincide(tmp_path):
    path = tmp_path / "actual.csv"
    io_seguro.escribir_atomico(str(path), "a,b,c\r\n", encoding="utf-8")
    assert io_seguro.verificar_contenido(str(path), "a,b,c\r\n", encoding="utf-8") is True


def test_verificar_contenido_no_coincide(tmp_path):
    path = tmp_path / "actual.csv"
    io_seguro.escribir_atomico(str(path), "a,b,c\r\n", encoding="utf-8")
    # Simula el escenario que motiva esta verificación: el archivo en disco
    # quedó truncado/alterado respecto de lo que el motor esperaba escribir.
    assert io_seguro.verificar_contenido(str(path), "a,b,c,d\r\n", encoding="utf-8") is False


def test_verificar_contenido_archivo_inexistente(tmp_path):
    path = tmp_path / "no_existe.csv"
    assert io_seguro.verificar_contenido(str(path), "cualquier cosa", encoding="utf-8") is False


def test_verificar_contenido_respeta_bom(tmp_path):
    path = tmp_path / "con_bom.csv"
    io_seguro.escribir_atomico(str(path), "código,1\r\n", encoding="utf-8-sig")
    assert io_seguro.verificar_contenido(str(path), "código,1\r\n", encoding="utf-8-sig") is True
