from pathlib import Path

import pytest

from app.ai.recetas_por_area import cargar_catalogo, generar_por_area
from app.ai.plantillas_masivas import leer_listado

REPO_ROOT = Path(__file__).resolve().parents[2]
RECETAS_DIR = REPO_ROOT / "docs" / "Recetas"
LISTADO_PATH = REPO_ROOT / "docs" / "Recetas_Andon.txt"

_AREAS = {"HD": "RecetasHD", "GPS1": "RecetasGPS1", "GPS2": "RecetasGPS2"}


def _catalogos() -> dict[str, object]:
    from app.ai.plantillas_masivas import _normalizar

    return {
        _normalizar(area): cargar_catalogo(RECETAS_DIR / carpeta, area)
        for area, carpeta in _AREAS.items()
    }


def test_catalogo_hd_tiene_los_4_sufijos_confirmados():
    catalogo = cargar_catalogo(RECETAS_DIR / "RecetasHD", "HD")
    assert sorted(v.sufijo for v in catalogo.variantes) == ["15", "17", "19", "28"]


def test_catalogo_gps1_tiene_los_5_sufijos_confirmados():
    catalogo = cargar_catalogo(RECETAS_DIR / "RecetasGPS1", "GPS1")
    assert sorted(v.sufijo for v in catalogo.variantes) == ["14", "15", "17", "19", "26"]


def test_catalogo_gps2_tiene_los_3_sufijos():
    catalogo = cargar_catalogo(RECETAS_DIR / "RecetasGPS2", "GPS2")
    assert sorted(v.sufijo for v in catalogo.variantes) == ["13.5", "15", "17"]


def test_catalogo_ignora_subcarpetas_nuevo_nuevos_obsoletos():
    # RecetasHD/Nuevo tiene 001789002254.{15,17,19}, RecetasGPS2/Obsoletos
    # tiene sufijos .24/.20 que no deben aparecer en el catalogo
    catalogo_gps2 = cargar_catalogo(RECETAS_DIR / "RecetasGPS2", "GPS2")
    assert "24" not in [v.sufijo for v in catalogo_gps2.variantes]
    assert "20" not in [v.sufijo for v in catalogo_gps2.variantes]


def test_caso_real_recetas_andon():
    catalogos = _catalogos()
    encabezados, filas = leer_listado(LISTADO_PATH.read_bytes(), LISTADO_PATH.name)

    resultado = generar_por_area(catalogos, encabezados, filas)

    # Recetas_Andon.txt: 12 filas de area HD, 2 de area GPS2, 0 de GPS1
    assert resultado.areas_usadas == {"HD": 12, "GPS2": 2}
    assert resultado.filas_sin_area == []
    # HD: 12 filas x 4 sufijos = 48 ; GPS2: 2 filas x 3 sufijos = 6
    assert len(resultado.archivos) == 48 + 6

    nombres = {a.nombre_archivo for a in resultado.archivos}
    assert "001789002162.13.5.def.txt" in nombres   # primera fila, area GPS2
    assert "001789002361.15.def.txt" in nombres     # segunda fila, area HD


def test_contenido_reemplaza_solo_codigo_y_descripcion():
    catalogos = _catalogos()
    encabezados, filas = leer_listado(LISTADO_PATH.read_bytes(), LISTADO_PATH.name)
    resultado = generar_por_area(catalogos, encabezados, filas)

    archivo = next(a for a in resultado.archivos if a.nombre_archivo == "001789002361.15.def.txt")
    lineas = archivo.contenido.splitlines()
    assert lineas[0] == "#Codigo;001789002361"
    assert lineas[1] == "#Operacion;15"
    assert lineas[2] == "#Descripcion;471700021861"
    assert "* #Maquina;<idMaquinas>;<default>;<GPH>;<TEP>;<MUL>;<DIV>" in archivo.contenido
    assert "#Maquina;1200001;True;;15.80;1;1" in archivo.contenido
    assert "\r\n" in archivo.contenido  # preserva CRLF del archivo de referencia


def test_fila_con_area_desconocida_no_bloquea_el_resto():
    catalogos = _catalogos()
    contenido = (
        "amortiguador;sellado;area\n"
        "111;222;HD\n"
        "333;444;ZONA_INEXISTENTE\n"
    ).encode()
    encabezados, filas = leer_listado(contenido, "listado.csv")

    resultado = generar_por_area(catalogos, encabezados, filas)

    assert resultado.filas_sin_area == [2]
    assert resultado.areas_usadas == {"HD": 1}
    assert len(resultado.archivos) == 4  # solo la fila 1 (HD tiene 4 sufijos)


def test_falta_columna_sellado_amortiguador_o_area_lanza_error():
    catalogos = _catalogos()
    contenido = b"amortiguador;area\n111;HD\n"
    encabezados, filas = leer_listado(contenido, "listado.csv")
    with pytest.raises(ValueError):
        generar_por_area(catalogos, encabezados, filas)


def test_nombres_duplicados_dentro_de_la_misma_area_agregan_sufijo():
    catalogos = {"hd": cargar_catalogo(RECETAS_DIR / "RecetasHD", "HD")}
    encabezados = ["sellado", "amortiguador", "area"]
    filas = [
        {"sellado": "X", "amortiguador": "A", "area": "HD"},
        {"sellado": "X", "amortiguador": "B", "area": "HD"},
    ]
    resultado = generar_por_area(catalogos, encabezados, filas)
    nombres = sorted(a.nombre_archivo for a in resultado.archivos)
    assert "X.15.def.txt" in nombres
    assert "X.15_2.def.txt" in nombres
