"""
test_synthetic.py — casos de round-trip con fixtures 100% sintéticos.
======================================================================
A diferencia de test_engine.py, ninguno de estos casos depende de los CSV
reales de planta (recetas232.csv, record_EXPORT.csv, etc.) — usan datos
inventados en el propio test. Esto permite:

  1. Correr la red de seguridad completa en cualquier máquina/CI aunque los
     CSV reales no estén disponibles (o se saquen del repo).
  2. Cubrir variantes de formato (CRLF/LF/CR, con/sin BOM, delimitador ','
     o ';', campos ocultos, placeholders) que los archivos reales de la 232
     no necesariamente ejercitan todas a la vez.
  3. Verificar explícitamente el invariante "_raw alineado con records" tras
     una secuencia larga de altas/bajas/modificaciones (Nivel 0.3 del plan
     de mejoras).
"""

import os
import sys
import tempfile

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "src"))

from profile import Profile  # noqa: E402
from datastore import DataStore  # noqa: E402


def _perfil_columnas(fin_de_linea="CRLF", bom=False, delimitador=",",
                      con_oculto=False, con_placeholder=False):
    """Perfil transpuesto sintético: 1 fila clave + 2 parámetros, con
    variantes opcionales de campo oculto y placeholder."""
    campos = [
        {"nombre_interno": "code", "rol": "clave", "fila": 0,
         "etiqueta": "Codigo", "tipo": "texto", "titulo_ui": "Código"},
        {"nombre_interno": "color", "rol": "parametro", "fila": 1,
         "etiqueta": "Color", "tipo": "entero", "titulo_ui": "Color",
         "min": 1, "max": 9, "default": 1},
        {"nombre_interno": "peso", "rol": "parametro", "fila": 2,
         "etiqueta": "Peso", "tipo": "decimal", "titulo_ui": "Peso",
         # separador "." a propósito: no debe chocar con el delimitador de
         # columnas parametrizado (',' o ';') en estos tests.
         "formato": {"separador_decimal": ".", "decimales": 2}},
    ]
    estructura = {"columna_etiquetas": 0, "primera_columna_datos": 1,
                  "filas_fijas": [], "fila_indice": None}
    if con_oculto:
        campos.append({
            "nombre_interno": "oculto", "rol": "parametro", "fila": 3,
            "etiqueta": "Interno", "tipo": "texto", "titulo_ui": "Interno",
            "visible": False,
        })
    features = {}
    if con_placeholder:
        features["placeholder"] = {"patron": r"^_VACIO_\d+$", "generar": "_VACIO_{n}"}

    data = {
        "id": "synth", "nombre": "Sintético", "descripcion": "",
        "archivo_inicial": "",
        "archivo": {"extension": "csv", "delimitador": delimitador,
                    "encoding": "utf-8", "bom": bom,
                    "fin_de_linea": fin_de_linea, "orientacion": "columnas"},
        "estructura": estructura,
        "campos": campos,
        "features": features,
    }
    return Profile.from_dict(data)


def _escribir(tmp_path, contenido: str, encoding: str, newline: str = "") -> None:
    with open(tmp_path, "w", encoding=encoding, newline=newline) as f:
        f.write(contenido)


@pytest.mark.parametrize("fin_de_linea,terminador", [
    ("CRLF", "\r\n"),
    ("LF", "\n"),
    ("CR", "\r"),
])
def test_roundtrip_variantes_fin_de_linea(tmp_path, fin_de_linea, terminador):
    prof = _perfil_columnas(fin_de_linea=fin_de_linea)
    filas = [
        ["Codigo", "A1", "A2"],
        ["Color", "1", "2"],
        ["Peso", "1.50", "2.25"],
    ]
    texto = terminador.join(",".join(f) for f in filas) + terminador
    path = tmp_path / "sintetico.csv"
    _escribir(path, texto, prof.encoding)

    store = DataStore.load(str(path), prof)
    assert len(store.records) == 2
    regenerado = store.to_text().encode(prof.encoding)
    with open(path, "rb") as f:
        original = f.read()
    assert original == regenerado, f"round-trip byte-perfecto con fin_de_linea={fin_de_linea}"


def test_roundtrip_con_bom():
    prof = _perfil_columnas(bom=True)
    filas = [
        ["Codigo", "A1", "A2"],
        ["Color", "1", "2"],
        ["Peso", "1.50", "2.25"],
    ]
    texto = "\r\n".join(",".join(f) for f in filas) + "\r\n"
    tmp = os.path.join(tempfile.gettempdir(), "sintetico_bom.csv")
    with open(tmp, "w", encoding="utf-8-sig", newline="") as f:
        f.write(texto)
    try:
        with open(tmp, "rb") as f:
            original = f.read()
        assert original.startswith(b"\xef\xbb\xbf"), "el fixture realmente tiene BOM"

        store = DataStore.load(tmp, prof)
        assert len(store.records) == 2
        regenerado = store.to_text().encode("utf-8-sig" if prof.bom else prof.encoding)
        assert original == regenerado, "round-trip byte-perfecto conservando el BOM"
    finally:
        os.remove(tmp)


@pytest.mark.parametrize("delimitador", [",", ";"])
def test_roundtrip_delimitadores(tmp_path, delimitador):
    prof = _perfil_columnas(delimitador=delimitador)
    filas = [
        ["Codigo", "A1", "A2"],
        ["Color", "1", "2"],
        ["Peso", "1.50", "2.25"],
    ]
    texto = "\r\n".join(delimitador.join(f) for f in filas) + "\r\n"
    path = tmp_path / "sintetico_delim.csv"
    _escribir(path, texto, prof.encoding)

    store = DataStore.load(str(path), prof)
    assert len(store.records) == 2
    regenerado = store.to_text().encode(prof.encoding)
    with open(path, "rb") as f:
        original = f.read()
    assert original == regenerado, f"round-trip byte-perfecto con delimitador={delimitador!r}"


def test_roundtrip_con_campo_oculto(tmp_path):
    prof = _perfil_columnas(con_oculto=True)
    filas = [
        ["Codigo", "A1", "A2"],
        ["Color", "1", "2"],
        ["Peso", "1.50", "2.25"],
        ["Interno", "SECRETO-1", "SECRETO-2"],
    ]
    texto = "\r\n".join(",".join(f) for f in filas) + "\r\n"
    path = tmp_path / "sintetico_oculto.csv"
    _escribir(path, texto, prof.encoding)

    store = DataStore.load(str(path), prof)
    assert all("oculto" != c.nombre_interno for c in prof.campos_visibles()), \
        "el campo oculto no aparece entre los visibles"
    assert store.records[0]["oculto"] == "SECRETO-1", \
        "el campo oculto SÍ viaja con el registro (aunque no se muestre)"

    regenerado = store.to_text().encode(prof.encoding)
    with open(path, "rb") as f:
        original = f.read()
    assert original == regenerado, "round-trip byte-perfecto con campo oculto sin tocar"

    # Editar el registro sin tocar el campo oculto: debe seguir viajando crudo.
    store.update(0, {"color": 5})
    grid = store.to_grid()
    assert grid[3][1] == "SECRETO-1", \
        "el campo oculto se preserva crudo tras editar OTRO campo del mismo registro"


def test_roundtrip_con_placeholders(tmp_path):
    prof = _perfil_columnas(con_placeholder=True)
    # El slot vacío va en el MEDIO (no al final): la fila clave recorta las
    # celdas vacías finales (ver DataStore._parse_columnas), así que un
    # placeholder al final del archivo ni siquiera contaría como registro —
    # el caso real de planta es slots reservados intercalados entre piezas.
    filas = [
        ["Codigo", "A1", "", "A3"],
        ["Color", "1", "", "3"],
        ["Peso", "1.50", "", "3.50"],
    ]
    texto = "\r\n".join(",".join(f) for f in filas) + "\r\n"
    path = tmp_path / "sintetico_placeholder.csv"
    _escribir(path, texto, prof.encoding)

    store = DataStore.load(str(path), prof)
    assert len(store.records) == 3, "carga también el slot vacío intercalado"
    assert store.is_placeholder(store.records[1]), "el slot vacío se reconoce como placeholder"
    assert store.count_real() == 2, "count_real excluye el placeholder"

    # OJO: acá NO hay round-trip byte-perfecto por diseño. La celda de código
    # vacía se normaliza a un id generado ("_VACIO_{n}") apenas se carga (ver
    # DataStore._parse_columnas), así que el archivo regenerado difiere del
    # original en esa celda — es la única excepción intencional al
    # raw-preserve, documentada en profile.py (feature 'placeholder').
    assert store.records[1]["code"] == "_VACIO_2", \
        "el slot vacío recibe el id generado por el patrón de placeholder"
    regenerado = store.to_text()
    assert "_VACIO_2" in regenerado, \
        "el id generado para el placeholder se escribe al guardar"
    # El resto de las celdas de ese registro (no clave) sí se preserva crudo
    # (siguen vacías, no se les inventa ningún valor).
    assert "Color,1,,3\r\n" in regenerado, \
        "las celdas no-clave del slot vacío se preservan crudas (vacías)"


def test_raw_alineado_tras_secuencia_larga_de_crud():
    """Invariante crítico: self._raw debe quedar SIEMPRE alineado por índice
    con self.records, sin importar la secuencia de add/update/delete. Si se
    desalinean, una celda no editada podría reescribirse con el string crudo
    de OTRO registro — corrupción silenciosa de datos ajenos al que se editó."""
    prof = _perfil_columnas()
    store = DataStore(prof, [])

    # Secuencia deliberadamente intercalada de altas, bajas y ediciones.
    for i in range(20):
        store.add(store.nuevo_registro({"code": f"C{i}", "color": (i % 9) + 1,
                                         "peso": float(i)}))
    assert len(store.records) == len(store._raw) == 20

    for i in (17, 3, 9, 0):
        store.delete(i)
    assert len(store.records) == len(store._raw) == 16

    # Identificamos los registros a editar por CÓDIGO (no por índice: los
    # índices se van a seguir moviendo con los add/delete posteriores, y
    # justamente lo que este test valida es que la edición viaja con el
    # registro correcto pase lo que pase con su posición).
    idx_a, idx_b = 2, 5
    code_a = store.records[idx_a]["code"]
    code_b = store.records[idx_b]["code"]
    store.update(idx_a, {"color": 7})
    store.update(idx_b, {"peso": 99.5})
    assert len(store.records) == len(store._raw) == 16

    for i in range(3):
        store.add(store.nuevo_registro({"code": f"NUEVO{i}", "color": 1, "peso": 1.0}))
    store.delete(1)
    assert len(store.records) == len(store._raw) == 18

    # Cada _raw[i] debe corresponder al registro records[i]: verificamos
    # indirectamente serializando y recargando, y comprobando que las claves
    # coinciden en el mismo orden (si _raw estuviera desalineado, alguna
    # celda no editada mostraría el código/valor de otro registro).
    tmp = os.path.join(tempfile.gettempdir(), "raw_alineado_test.csv")
    store.save(tmp)
    try:
        recargado = DataStore.load(tmp, prof)
        assert [r["code"] for r in recargado.records] == [r["code"] for r in store.records], \
            "el orden y contenido de claves se preserva tras guardar con _raw intercalado"
        by_code = {r["code"]: r for r in recargado.records}
        assert by_code[code_a]["color"] == 7, \
            f"la edición de color en el registro {code_a} persistió pese a add/delete posteriores"
        assert by_code[code_b]["peso"] == 99.5, \
            f"la edición de peso en el registro {code_b} persistió pese a add/delete posteriores"
    finally:
        os.remove(tmp)


def test_add_delete_no_desalinea_raw_de_registros_no_tocados():
    """Reproduce específicamente el riesgo: agregar y borrar registros no
    debe hacer que un registro NO editado empiece a reformatearse con
    _format_value() en vez de conservar su string crudo original."""
    prof = _perfil_columnas()
    tmp = os.path.join(tempfile.gettempdir(), "raw_no_tocado.csv")
    filas = [
        ["Codigo", "A1", "A2", "A3"],
        ["Color", "1", "2", "3"],
        ["Peso", "1.500", "2.250", "3.000"],  # 3 decimales: distinto del 'formato' (2)
    ]
    _escribir(tmp, "\r\n".join(",".join(f) for f in filas) + "\r\n", prof.encoding)
    try:
        store = DataStore.load(tmp, prof)
        # Insertamos y borramos registros ANTES del que nos interesa (índice 1, A2).
        store.add(store.nuevo_registro({"code": "NUEVO", "color": 5, "peso": 5.0}))
        store.delete(0)  # ahora A2 pasó de índice 1 a índice 0
        grid = store.to_grid()
        # A2 no fue editado nunca: su celda de Peso debe seguir siendo el
        # string crudo original "2.250" (3 decimales), NO reformateada a
        # "2.25" (2 decimales, según 'formato') — eso confirmaría que _raw
        # se corrió de índice al hacer add()/delete().
        assert grid[2][1] == "2.250", \
            "el registro no tocado conserva su celda cruda pese a add()+delete() previos"
    finally:
        os.remove(tmp)
