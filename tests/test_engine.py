"""
test_engine.py — red de seguridad del motor genérico (Fase 0 + Fase 1)
======================================================================
Se corre con:  py tests/test_engine.py

Verifica, entre otras cosas, que cargar y volver a guardar un archivo con el
motor nuevo + perfil 232 produzca BYTES IDÉNTICOS al original (crítico: ese
archivo se sube al HMI de la máquina).
"""

import os
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "src"))

from profile import Profile, ProfileError          # noqa: E402
from datastore import DataStore                     # noqa: E402
from metadata import Sidecar                         # noqa: E402
import profile_builder as PB                          # noqa: E402

PROFILE_232 = os.path.join(ROOT, "profiles", "maquina_232.json")
CSV_LIMPIO = os.path.join(ROOT, "recetas232.csv")
CSV_FABRICA = os.path.join(ROOT, "recetas232_backup_original.csv")
CSV_EXPORT = os.path.join(ROOT, "record_EXPORT.csv")

_fails = []


def check(cond, msg):
    if cond:
        print(f"  OK  {msg}")
    else:
        print(f" FAIL {msg}")
        _fails.append(msg)


def golden_roundtrip(path, label):
    """Cargar -> guardar debe reproducir el archivo byte por byte."""
    if not os.path.exists(path):
        print(f"  (omitido: no existe {label})")
        return
    with open(path, "rb") as f:
        original = f.read()
    prof = Profile.load(PROFILE_232)
    store = DataStore.load(path, prof)
    regenerado = store.to_text().encode(prof.encoding)
    check(original == regenerado,
          f"round-trip byte-perfecto: {label} ({len(original)} bytes)")
    if original != regenerado:
        for i, (a, b) in enumerate(zip(original, regenerado)):
            if a != b:
                print(f"      primer diff en byte {i}: "
                      f"{original[max(0,i-12):i+12]!r} vs {regenerado[max(0,i-12):i+12]!r}")
                break


def test_perfil():
    print("\n[Perfil]")
    prof = Profile.load(PROFILE_232)
    check(prof.id == "232", "carga el perfil 232")
    check(prof.orientacion == "columnas", "orientacion = columnas")
    check(prof.fin_de_linea == "\r\n", "fin de línea CRLF resuelto")
    check(prof.campo_clave().nombre_interno == "code", "campo clave = code")
    check(len(prof.parametros()) == 3, "3 parámetros (color, grams, speed)")


def test_perfil_invalido():
    print("\n[Validación de perfil]")
    base = {
        "id": "x", "archivo": {"orientacion": "columnas"},
        "estructura": {"filas_fijas": [{"fila": 0, "celdas": ["a"]}]},
        "campos": [{"nombre_interno": "code", "rol": "clave", "fila": 2}],
    }
    # Falta la fila 1 (hueco entre 0 y 2)
    try:
        Profile.from_dict(base)
        check(False, "detecta hueco de filas")
    except ProfileError:
        check(True, "detecta hueco de filas")

    # Sin campo clave
    base2 = {
        "id": "x", "archivo": {"orientacion": "columnas"},
        "estructura": {},
        "campos": [{"nombre_interno": "color", "rol": "parametro", "fila": 0}],
    }
    try:
        Profile.from_dict(base2)
        check(False, "detecta falta de campo clave")
    except ProfileError:
        check(True, "detecta falta de campo clave")


def test_golden():
    print("\n[Round-trip byte-perfecto]")
    golden_roundtrip(CSV_FABRICA, "recetas232_backup_original.csv (fábrica)")
    golden_roundtrip(CSV_LIMPIO, "recetas232.csv (limpio)")


def test_carga_datos():
    print("\n[Carga de datos]")
    prof = Profile.load(PROFILE_232)
    store = DataStore.load(CSV_LIMPIO, prof)
    check(len(store.records) > 0, f"carga {len(store.records)} registros")
    r0 = store.records[0]
    check(set(r0.keys()) == {"code", "color", "grams", "speed"},
          "cada registro tiene los 4 campos del perfil")
    check(isinstance(r0["code"], str), "code es texto (conserva ceros)")
    check(isinstance(r0["color"], int), "color es entero")


def test_crud():
    print("\n[CRUD]")
    prof = Profile.load(PROFILE_232)
    store = DataStore.load(CSV_LIMPIO, prof)
    n0 = len(store.records)

    nuevo = store.nuevo_registro({"code": "TEST-999", "grams": 123, "speed": 280})
    check(nuevo["color"] == 1, "nuevo_registro aplica default de color (1)")
    check(nuevo["speed"] == 280, "nuevo_registro respeta valores dados")
    store.add(nuevo)
    check(store.find_key("TEST-999") == n0, "add + find_key")

    store.update(0, {"code": "MOD-000", "grams": 5})
    check(store.records[0]["code"] == "MOD-000", "update cambia la clave")
    check(store.records[0]["grams"] == 5, "update cambia un parámetro")

    store.delete(0)
    check(len(store.records) == n0, "delete (quedamos en n0 tras add+delete)")

    # round-trip tras CRUD: índices secuenciales y ancho consistente
    tmp = os.path.join(tempfile.gettempdir(), "crud_test.csv")
    store.save(tmp)
    store2 = DataStore.load(tmp, prof)
    check(len(store2.records) == len(store.records), "recarga tras CRUD")
    import csv
    with open(tmp, encoding="utf-8-sig", newline="") as f:
        rows = list(csv.reader(f))
    idx = rows[3][1:1 + len(store.records)]
    check(idx == [str(i) for i in range(1, len(store.records) + 1)],
          "fila índice renumerada secuencial")
    check(len({len(r) for r in rows}) == 1, "todas las filas tienen igual ancho")
    os.remove(tmp)


def test_duplicados():
    print("\n[Duplicados genéricos]")
    prof = Profile.load(PROFILE_232)
    store = DataStore.load(CSV_LIMPIO, prof)
    groups = store.find_similar_groups()
    check(len(groups) == 25, f"detecta 25 grupos por 'ignorar_ceros' (hay {len(groups)})")

    # excluir una clave (como haría el sidecar 'no_duplicado')
    if groups:
        clave = store.records[groups[0][0]]["code"]
        groups2 = store.find_similar_groups(excluded_keys=frozenset({clave}))
        codes2 = {store.records[i]["code"] for g in groups2 for i in g}
        check(clave not in codes2, "excluye claves marcadas como no-duplicado")


def test_placeholders():
    print("\n[Placeholders]")
    prof = Profile.load(PROFILE_232)
    store = DataStore.load(CSV_FABRICA, prof) if os.path.exists(CSV_FABRICA) \
        else DataStore.load(CSV_LIMPIO, prof)
    total = len(store.records)
    reales = store.count_real()
    check(reales <= total, f"count_real={reales} de total={total}")
    if os.path.exists(CSV_FABRICA):
        check(total == 1743 and reales == 673,
              "fábrica: 1743 slots, 673 piezas reales")


def test_sidecar():
    print("\n[Sidecar de metadatos]")
    tmp = os.path.join(tempfile.gettempdir(), "meta_test.json")
    if os.path.exists(tmp):
        os.remove(tmp)
    sc = Sidecar.load(tmp)
    sc.set("A121538", "no_duplicado", True)
    sc.save()
    sc2 = Sidecar.load(tmp)
    check(sc2.get("A121538", "no_duplicado") is True, "guarda y recarga flag")
    check(sc2.keys_with("no_duplicado") == frozenset({"A121538"}),
          "keys_with devuelve las marcadas")
    sc2.rename_key("A121538", "A999")
    check(sc2.get("A999", "no_duplicado") is True, "rename_key mueve el flag")
    os.remove(tmp)


def test_orientacion_filas():
    print("\n[Orientación 'filas' (CSV normal, sintético)]")
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
    check(len(store.records) == 2, "carga 2 filas")
    check(store.records[0]["code"] == "00123", "conserva ceros en clave (filas)")
    check(store.records[1]["temp"] == 90, "parámetro entero (filas)")
    check(store.to_text() == csv_text, "round-trip exacto (filas)")
    os.remove(tmp)


def test_tipos_extendidos_raw_preserve():
    """record_EXPORT.csv es un formato de otra máquina de la planta con
    celdas que el motor viejo destruía: ceros a la izquierda (RECETAS_
    CILINDRO), decimales de ancho variable con coma (16 y 7 decimales según
    el campo) y centinelas de texto mezclados en columnas numéricas (N/C,
    PATRON). Ejercita 'entero_ceros', 'decimal' con formato explícito, campos
    ocultos (visible=False) y el modelo raw-preserve."""
    print("\n[Tipos extendidos + raw-preserve: record_EXPORT.csv]")
    if not os.path.exists(CSV_EXPORT):
        print(f"  (omitido: no existe {CSV_EXPORT})")
        return

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
    check(len(prof.campos) == 11, "perfil: 11 campos (10 visibles + 1 oculto)")
    check(len(prof.campos_visibles()) == 10, "perfil: campos_visibles excluye el oculto")

    with open(CSV_EXPORT, "rb") as f:
        original = f.read()
    store = DataStore.load(CSV_EXPORT, prof)
    check(len(store.records) > 0, f"carga {len(store.records)} registros")
    check(store.records[0]["cilindro"] == 0,
          "'PATRON' en campo entero_ceros cae al default sin romper la carga")
    check(store.records[0]["lanza"] == "N/C",
          "centinela 'N/C' preservado como texto en el valor tipado")

    regenerado = store.to_text().encode(prof.encoding)
    check(original == regenerado,
          f"round-trip byte-perfecto SIN editar: record_EXPORT.csv ({len(original)} bytes)")
    if original != regenerado:
        for i, (a, b) in enumerate(zip(original, regenerado)):
            if a != b:
                print(f"      primer diff en byte {i}: "
                      f"{original[max(0,i-12):i+12]!r} vs {regenerado[max(0,i-12):i+12]!r}")
                break

    # Editar dos celdas: deben reformatearse según 'formato'; el resto debe
    # seguir byte-idéntico al original (raw-preserve de las no tocadas).
    store.update(1, {"cilindro": 42, "diam_int": 12.5})
    grid = store.to_grid()
    check(grid[5][2] == "000000000042",
          "entero_ceros editado: rellena con ceros a ancho 12")
    check(grid[6][2] == "12,5000000000000000",
          "decimal editado: separador ',' y 16 decimales")
    check(grid[7][2] == "29,0000000000000000",
          "campo NO tocado (diam_ext) conserva el string crudo original")
    check(grid[2][1] == "PATRON",
          "campo oculto (langid) sigue viajando con el registro y se preserva")

    # add()/delete() deben mantener _raw alineado con records.
    n0 = len(store.records)
    nuevo = store.nuevo_registro({"code": "NUEVO1", "cilindro": 5, "diam_int": 1.25})
    store.add(nuevo)
    check(len(store._raw) == len(store.records), "add() mantiene _raw alineado")
    store.delete(0)
    check(len(store.records) == n0 and len(store._raw) == len(store.records),
          "delete() mantiene _raw alineado")

    tmp = os.path.join(tempfile.gettempdir(), "export_test_crud.csv")
    store.save(tmp)
    store2 = DataStore.load(tmp, prof)
    check(len(store2.records) == len(store.records), "recarga tras CRUD (tipos extendidos)")
    os.remove(tmp)


def test_profile_builder():
    print("\n[profile_builder: alta de máquina nueva]")
    import csv

    # --- filas (CSV normal) ---
    tmp1 = os.path.join(tempfile.gettempdir(), "pb_test_filas.csv")
    with open(tmp1, "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(["Codigo", "Temp", "Presion"])
        w.writerow(["A1", "45", "1.5"])
        w.writerow(["A2", "50", "2.0"])
    scaffold = PB.build_scaffold("pbtest1", "PB Test Filas", "", "pb_test_filas.csv",
                                 tmp1, "filas")
    prof = Profile.from_dict(scaffold)
    check(prof.campo_clave().nombre_interno == "codigo",
          "filas: primera columna queda como clave")
    check(len(prof.parametros()) == 2, "filas: 2 parámetros detectados")
    store = DataStore.load(tmp1, prof)
    check(len(store.records) == 2, "filas: carga 2 registros con el motor real")
    check(store.records[0]["temp"] == 45 and isinstance(store.records[0]["temp"], int),
          "filas: tipo entero detectado por muestreo")
    check(store.records[0]["presion"] == 1.5, "filas: tipo decimal detectado por muestreo")
    os.remove(tmp1)

    # --- columnas (transpuesta, usando datos reales de la 232) ---
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
    check(len(prof2.campos) == len(subset), "columnas: un campo por cada fila del CSV")
    store2 = DataStore.load(tmp2, prof2)
    check(len(store2.records) == 5, "columnas: carga 5 registros (piezas)")

    # fila de clave fuera de rango debe fallar con un error claro
    try:
        PB.build_scaffold("pbtest3", "x", "", "x.csv", tmp2, "columnas", clave_row=999)
        check(False, "columnas: rechaza fila de clave fuera de rango")
    except ValueError:
        check(True, "columnas: rechaza fila de clave fuera de rango")
    os.remove(tmp2)


def main():
    test_perfil()
    test_perfil_invalido()
    test_golden()
    test_tipos_extendidos_raw_preserve()
    test_carga_datos()
    test_crud()
    test_duplicados()
    test_placeholders()
    test_sidecar()
    test_orientacion_filas()
    test_profile_builder()
    print("\n" + "=" * 60)
    if _fails:
        print(f"RESULTADO: {len(_fails)} prueba(s) FALLARON")
        for m in _fails:
            print("  -", m)
        sys.exit(1)
    print("RESULTADO: TODAS LAS PRUEBAS PASARON")


if __name__ == "__main__":
    main()
