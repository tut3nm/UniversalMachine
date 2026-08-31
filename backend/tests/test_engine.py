"""
test_engine.py — red de seguridad del motor genérico (Fase 0 + Fase 1)
======================================================================
Se corre con:  pytest tests/test_engine.py   (o simplemente: pytest)
También sigue funcionando como script suelto:  py tests/test_engine.py

Verifica, entre otras cosas, que cargar y volver a guardar un archivo con el
motor nuevo + perfil 232 produzca BYTES IDÉNTICOS al original (crítico: ese
archivo se sube al HMI de la máquina).
"""

import csv
import os
import sys
import tempfile

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "app", "core"))

from profile import Profile, ProfileError          # noqa: E402
from datastore import DataStore                     # noqa: E402
from metadata import Sidecar                         # noqa: E402
import profile_builder as PB                          # noqa: E402

PROFILE_232 = os.path.join(ROOT, "profiles", "maquina_232.json")
# recetas232.csv es también el archivo_inicial embebido en el perfil 232 y
# se anonimiza en el lugar; los otros dos son fixtures puros de test, viven
# en tests/fixtures/. Los tres son muestras anonimizadas (mismo formato y
# cantidad de filas que los datos reales, códigos/valores ficticios) — ver
# scripts/anonymize_csv.py y PLAN_MEJORAS.md Nivel 0.1.
CSV_LIMPIO = os.path.join(ROOT, "recetas232.csv")
CSV_FABRICA = os.path.join(ROOT, "tests", "fixtures", "recetas232_backup_original.csv")
CSV_EXPORT = os.path.join(ROOT, "tests", "fixtures", "record_EXPORT.csv")


def golden_roundtrip(path, label):
    """Cargar -> guardar debe reproducir el archivo byte por byte."""
    if not os.path.exists(path):
        pytest.skip(f"no existe {label}")
    with open(path, "rb") as f:
        original = f.read()
    prof = Profile.load(PROFILE_232)
    store = DataStore.load(path, prof)
    regenerado = store.to_text().encode(prof.encoding)
    if original != regenerado:
        for i, (a, b) in enumerate(zip(original, regenerado)):
            if a != b:
                pytest.fail(
                    f"round-trip NO byte-perfecto: {label} ({len(original)} bytes) — "
                    f"primer diff en byte {i}: "
                    f"{original[max(0,i-12):i+12]!r} vs {regenerado[max(0,i-12):i+12]!r}")
                break
        else:
            pytest.fail(f"round-trip NO byte-perfecto: {label} (largos distintos)")


def test_perfil():
    prof = Profile.load(PROFILE_232)
    assert prof.id == "232", "carga el perfil 232"
    assert prof.orientacion == "columnas", "orientacion = columnas"
    assert prof.fin_de_linea == "\r\n", "fin de línea CRLF resuelto"
    assert prof.campo_clave().nombre_interno == "code", "campo clave = code"
    assert len(prof.parametros()) == 3, "3 parámetros (color, grams, speed)"


def test_perfil_invalido_hueco_de_filas():
    base = {
        "id": "x", "archivo": {"orientacion": "columnas"},
        "estructura": {"filas_fijas": [{"fila": 0, "celdas": ["a"]}]},
        "campos": [{"nombre_interno": "code", "rol": "clave", "fila": 2}],
    }
    # Falta la fila 1 (hueco entre 0 y 2)
    with pytest.raises(ProfileError):
        Profile.from_dict(base)


def test_perfil_invalido_sin_clave():
    base = {
        "id": "x", "archivo": {"orientacion": "columnas"},
        "estructura": {},
        "campos": [{"nombre_interno": "color", "rol": "parametro", "fila": 0}],
    }
    with pytest.raises(ProfileError):
        Profile.from_dict(base)


def test_golden_fabrica():
    golden_roundtrip(CSV_FABRICA, "recetas232_backup_original.csv (fábrica)")


def test_golden_limpio():
    golden_roundtrip(CSV_LIMPIO, "recetas232.csv (limpio)")


def test_tipos_extendidos_raw_preserve():
    """record_EXPORT.csv es un formato de otra máquina de la planta con
    celdas que el motor viejo destruía: ceros a la izquierda (RECETAS_
    CILINDRO), decimales de ancho variable con coma (16 y 7 decimales según
    el campo) y centinelas de texto mezclados en columnas numéricas (N/C,
    PATRON). Ejercita 'entero_ceros', 'decimal' con formato explícito, campos
    ocultos (visible=False) y el modelo raw-preserve."""
    if not os.path.exists(CSV_EXPORT):
        pytest.skip(f"no existe {CSV_EXPORT}")

    perfil = {
        "id": "export_test", "nombre": "Export Test", "descripcion": "",
        "archivo_inicial": "",
        "archivo": {"extension": "csv", "delimitador": ";", "encoding": "utf-8",
                    "bom": False, "fin_de_linea": "CRLF", "orientacion": "columnas"},
        "estructura": {
            "columna_etiquetas": 0, "primera_columna_datos": 1,
            "filas_fijas": [
                {"fila": 0, "celdas": ["List separator=", "Decimal symbol=,"], "rellenar": True},
                {"fila": 1, "celdas": ["C.VALVULAS "], "rellenar": True},
            ],
            "fila_indice": {"fila": 3, "etiqueta": "1", "base": 1},
        },
        "campos": [
            {"nombre_interno": "langid", "rol": "parametro", "fila": 2,
             "etiqueta": "LANGID_409", "tipo": "texto", "titulo_ui": "LangID",
             "visible": False},
            {"nombre_interno": "code", "rol": "clave", "fila": 4,
             "etiqueta": "RECETAS_CODIGO", "tipo": "texto", "titulo_ui": "Código"},
            {"nombre_interno": "cilindro", "rol": "parametro", "fila": 5,
             "etiqueta": "RECETAS_CILINDRO", "tipo": "entero_ceros",
             "titulo_ui": "Cilindro", "formato": {"ancho": 12}},
            {"nombre_interno": "diam_int", "rol": "parametro", "fila": 6,
             "etiqueta": "RECETAS_DIAMETRO_INT", "tipo": "decimal",
             "titulo_ui": "Diámetro Int",
             "formato": {"separador_decimal": ",", "decimales": 16}},
            {"nombre_interno": "diam_ext", "rol": "parametro", "fila": 7,
             "etiqueta": "RECETAS_DIAMETRO_EXT", "tipo": "decimal",
             "titulo_ui": "Diámetro Ext",
             "formato": {"separador_decimal": ",", "decimales": 16}},
            {"nombre_interno": "largo", "rol": "parametro", "fila": 8,
             "etiqueta": "RECETAS_LARGO", "tipo": "decimal", "titulo_ui": "Largo",
             "formato": {"separador_decimal": ",", "decimales": 16}},
            {"nombre_interno": "lanza", "rol": "parametro", "fila": 9,
             "etiqueta": "RECETAS_LANZA", "tipo": "texto", "titulo_ui": "Lanza"},
            {"nombre_interno": "pos_val", "rol": "parametro", "fila": 10,
             "etiqueta": "RECETAS_POS_VAL", "tipo": "texto", "titulo_ui": "Pos Val"},
            {"nombre_interno": "pos_mesa", "rol": "parametro", "fila": 11,
             "etiqueta": "RECETAS_POS_MESA", "tipo": "decimal", "titulo_ui": "Pos Mesa",
             "formato": {"separador_decimal": ",", "decimales": 16}},
            {"nombre_interno": "fuerza", "rol": "parametro", "fila": 12,
             "etiqueta": "RECETAS_FUERZA", "tipo": "decimal", "titulo_ui": "Fuerza",
             "formato": {"separador_decimal": ",", "decimales": 16}},
            {"nombre_interno": "prof_clavado", "rol": "parametro", "fila": 13,
             "etiqueta": "RECETAS_PROF_CLAVADO", "tipo": "decimal",
             "titulo_ui": "Prof. Clavado",
             "formato": {"separador_decimal": ",", "decimales": 7}},
        ],
    }
    prof = Profile.from_dict(perfil)
    assert len(prof.campos) == 11, "perfil: 11 campos (10 visibles + 1 oculto)"
    assert len(prof.campos_visibles()) == 10, "perfil: campos_visibles excluye el oculto"

    with open(CSV_EXPORT, "rb") as f:
        original = f.read()
    store = DataStore.load(CSV_EXPORT, prof)
    assert len(store.records) > 0, f"carga {len(store.records)} registros"
    assert store.records[0]["cilindro"] == 0, \
        "'PATRON' en campo entero_ceros cae al default sin romper la carga"
    assert store.records[0]["lanza"] == "N/C", \
        "centinela 'N/C' preservado como texto en el valor tipado"

    regenerado = store.to_text().encode(prof.encoding)
    assert original == regenerado, \
        f"round-trip byte-perfecto SIN editar: record_EXPORT.csv ({len(original)} bytes)"

    # Editar dos celdas: deben reformatearse según 'formato'; el resto debe
    # seguir byte-idéntico al original (raw-preserve de las no tocadas).
    store.update(1, {"cilindro": 42, "diam_int": 12.5})
    grid = store.to_grid()
    assert grid[5][2] == "000000000042", \
        "entero_ceros editado: rellena con ceros a ancho 12"
    assert grid[6][2] == "12,5000000000000000", \
        "decimal editado: separador ',' y 16 decimales"
    assert grid[7][2] == "32,0000000000000000", \
        "campo NO tocado (diam_ext) conserva el string crudo original"
    assert grid[2][1] == "PATRON", \
        "campo oculto (langid) sigue viajando con el registro y se preserva"

    # add()/delete() deben mantener _raw alineado con records.
    n0 = len(store.records)
    nuevo = store.nuevo_registro({"code": "NUEVO1", "cilindro": 5, "diam_int": 1.25})
    store.add(nuevo)
    assert len(store._raw) == len(store.records), "add() mantiene _raw alineado"
    store.delete(0)
    assert len(store.records) == n0 and len(store._raw) == len(store.records), \
        "delete() mantiene _raw alineado"

    tmp = os.path.join(tempfile.gettempdir(), "export_test_crud.csv")
    store.save(tmp)
    store2 = DataStore.load(tmp, prof)
    assert len(store2.records) == len(store.records), \
        "recarga tras CRUD (tipos extendidos)"
    os.remove(tmp)


def test_carga_datos():
    prof = Profile.load(PROFILE_232)
    store = DataStore.load(CSV_LIMPIO, prof)
    assert len(store.records) > 0, f"carga {len(store.records)} registros"
    r0 = store.records[0]
    assert set(r0.keys()) == {"code", "color", "grams", "speed"}, \
        "cada registro tiene los 4 campos del perfil"
    assert isinstance(r0["code"], str), "code es texto (conserva ceros)"
    assert isinstance(r0["color"], int), "color es entero"


def test_crud():
    prof = Profile.load(PROFILE_232)
    store = DataStore.load(CSV_LIMPIO, prof)
    n0 = len(store.records)

    nuevo = store.nuevo_registro({"code": "TEST-999", "grams": 123, "speed": 280})
    assert nuevo["color"] == 1, "nuevo_registro aplica default de color (1)"
    assert nuevo["speed"] == 280, "nuevo_registro respeta valores dados"
    store.add(nuevo)
    assert store.find_key("TEST-999") == n0, "add + find_key"

    store.update(0, {"code": "MOD-000", "grams": 5})
    assert store.records[0]["code"] == "MOD-000", "update cambia la clave"
    assert store.records[0]["grams"] == 5, "update cambia un parámetro"

    store.delete(0)
    assert len(store.records) == n0, "delete (quedamos en n0 tras add+delete)"

    # round-trip tras CRUD: índices secuenciales y ancho consistente
    tmp = os.path.join(tempfile.gettempdir(), "crud_test.csv")
    store.save(tmp)
    store2 = DataStore.load(tmp, prof)
    assert len(store2.records) == len(store.records), "recarga tras CRUD"
    with open(tmp, encoding="utf-8-sig", newline="") as f:
        rows = list(csv.reader(f))
    idx = rows[3][1:1 + len(store.records)]
    assert idx == [str(i) for i in range(1, len(store.records) + 1)], \
        "fila índice renumerada secuencial"
    assert len({len(r) for r in rows}) == 1, "todas las filas tienen igual ancho"
    os.remove(tmp)


def test_duplicados():
    prof = Profile.load(PROFILE_232)
    store = DataStore.load(CSV_LIMPIO, prof)
    groups = store.find_similar_groups()
    assert len(groups) == 25, f"detecta 25 grupos por 'ignorar_ceros' (hay {len(groups)})"

    # excluir una clave (como haría el sidecar 'no_duplicado')
    if groups:
        clave = store.records[groups[0][0]]["code"]
        groups2 = store.find_similar_groups(excluded_keys=frozenset({clave}))
        codes2 = {store.records[i]["code"] for g in groups2 for i in g}
        assert clave not in codes2, "excluye claves marcadas como no-duplicado"


def test_placeholders():
    prof = Profile.load(PROFILE_232)
    store = DataStore.load(CSV_FABRICA, prof) if os.path.exists(CSV_FABRICA) \
        else DataStore.load(CSV_LIMPIO, prof)
    total = len(store.records)
    reales = store.count_real()
    assert reales <= total, f"count_real={reales} de total={total}"
    if os.path.exists(CSV_FABRICA):
        assert total == 1743 and reales == 673, \
            "fábrica: 1743 slots, 673 piezas reales"


def test_sidecar():
    tmp = os.path.join(tempfile.gettempdir(), "meta_test.json")
    if os.path.exists(tmp):
        os.remove(tmp)
    sc = Sidecar.load(tmp)
    sc.set("A121538", "no_duplicado", True)
    sc.save()
    sc2 = Sidecar.load(tmp)
    assert sc2.get("A121538", "no_duplicado") is True, "guarda y recarga flag"
    assert sc2.keys_with("no_duplicado") == frozenset({"A121538"}), \
        "keys_with devuelve las marcadas"
    sc2.rename_key("A121538", "A999")
    assert sc2.get("A999", "no_duplicado") is True, "rename_key mueve el flag"
    os.remove(tmp)


def test_orientacion_filas():
    data = {
        "id": "demo", "nombre": "Demo filas",
        "archivo": {"orientacion": "filas", "delimitador": ",",
                    "fin_de_linea": "LF"},
        "estructura": {"fila_encabezado": 0, "primera_fila_datos": 1},
        "campos": [
            {"nombre_interno": "code", "rol": "clave", "columna": 0,
             "etiqueta": "Codigo", "tipo": "texto", "titulo_ui": "Código"},
            {"nombre_interno": "temp", "rol": "parametro", "columna": 1,
             "etiqueta": "Temperatura", "tipo": "entero", "titulo_ui": "Temp"},
        ],
    }
    prof = Profile.from_dict(data)
    csv_text = "Codigo,Temperatura\n00123,45\nABC,90\n"
    tmp = os.path.join(tempfile.gettempdir(), "filas_demo.csv")
    with open(tmp, "w", encoding="utf-8", newline="") as f:
        f.write(csv_text)
    store = DataStore.load(tmp, prof)
    assert len(store.records) == 2, "carga 2 filas"
    assert store.records[0]["code"] == "00123", "conserva ceros en clave (filas)"
    assert store.records[1]["temp"] == 90, "parámetro entero (filas)"
    assert store.to_text() == csv_text, "round-trip exacto (filas)"
    os.remove(tmp)


def test_profile_builder_filas():
    tmp1 = os.path.join(tempfile.gettempdir(), "pb_test_filas.csv")
    with open(tmp1, "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(["Codigo", "Temp", "Presion"])
        w.writerow(["A1", "45", "1.5"])
        w.writerow(["A2", "50", "2.0"])
    scaffold = PB.build_scaffold("pbtest1", "PB Test Filas", "", "pb_test_filas.csv",
                                 tmp1, "filas")
    prof = Profile.from_dict(scaffold)
    assert prof.campo_clave().nombre_interno == "codigo", \
        "filas: primera columna queda como clave"
    assert len(prof.parametros()) == 2, "filas: 2 parámetros detectados"
    store = DataStore.load(tmp1, prof)
    assert len(store.records) == 2, "filas: carga 2 registros con el motor real"
    assert store.records[0]["temp"] == 45 and isinstance(store.records[0]["temp"], int), \
        "filas: tipo entero detectado por muestreo"
    assert store.records[0]["presion"] == 1.5, "filas: tipo decimal detectado por muestreo"
    os.remove(tmp1)


def test_profile_builder_columnas():
    if not os.path.exists(CSV_LIMPIO):
        pytest.skip(f"no existe {CSV_LIMPIO}")
    with open(CSV_LIMPIO, encoding="utf-8-sig", newline="") as f:
        rows = list(csv.reader(f))
    subset = [row[:6] for row in rows]  # etiqueta + 5 piezas
    tmp2 = os.path.join(tempfile.gettempdir(), "pb_test_columnas.csv")
    with open(tmp2, "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f, lineterminator="\r\n")
        w.writerows(subset)
    scaffold2 = PB.build_scaffold("pbtest2", "PB Test Columnas", "",
                                  "pb_test_columnas.csv", tmp2, "columnas", clave_row=2)
    prof2 = Profile.from_dict(scaffold2)
    assert len(prof2.campos) == len(subset), "columnas: un campo por cada fila del CSV"
    store2 = DataStore.load(tmp2, prof2)
    assert len(store2.records) == 5, "columnas: carga 5 registros (piezas)"

    # fila de clave fuera de rango debe fallar con un error claro
    with pytest.raises(ValueError):
        PB.build_scaffold("pbtest3", "x", "", "x.csv", tmp2, "columnas", clave_row=999)
    os.remove(tmp2)


if __name__ == "__main__":
    sys.exit(pytest.main([os.path.abspath(__file__), "-v"]))
