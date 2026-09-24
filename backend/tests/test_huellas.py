from pathlib import Path

from app.ai import tablas_delimitadas as td
from app.ai.dsl.interprete import construir_contexto
from app.ai.memoria import huellas
from app.ai.plantillas_masivas import _normalizar, leer_listado, parsear_plantilla
from app.ai.recetas_por_area import cargar_catalogo

DOCS = Path(__file__).resolve().parents[2] / "docs" / "H1312"
_RECETAS_DIR = Path(__file__).resolve().parents[2] / "docs" / "Recetas"
_LISTADO_PATH = Path(__file__).resolve().parents[2] / "docs" / "Recetas_Andon.txt"
_AREAS = {"HD": "RecetasHD", "GPS1": "RecetasGPS1", "GPS2": "RecetasGPS2"}


def _lineas(nombre: str) -> list[str]:
    return td.decodificar((DOCS / nombre).read_bytes())


def test_dos_archivos_del_mismo_formato_dan_la_misma_huella():
    # PLAN_MEMORIA_FORMATOS.md, 5.1: comparten titulos en las mismas filas.
    a = huellas.huella_mediciones(_lineas("824902015333_280826_005.csv"))
    b = huellas.huella_mediciones(_lineas("824902015333_021224_000.csv"))
    assert a is not None and a == b


def test_archivo_de_otro_formato_da_otra_huella():
    # 006 empieza directamente en [Messprogrammseite 1]: sin el preambulo.
    a = huellas.huella_mediciones(_lineas("824902015333_280826_005.csv"))
    c = huellas.huella_mediciones(_lineas("824902015333_280826_006.csv"))
    assert a != c
    assert huellas.similitud_mediciones(a, c) < huellas.UMBRAL_SIMILITUD


def test_similitud_de_la_misma_huella_es_uno():
    a = huellas.huella_mediciones(_lineas("824902015333_280826_005.csv"))
    assert huellas.similitud_mediciones(a, a) == 1.0


def test_archivo_sin_separador_no_tiene_huella():
    assert huellas.huella_mediciones(["esto no tiene comas ni nada"]) is None


# -- plantilla ------------------------------------------------------------------

_PLANTILLA_TXT = (
    "#Codigo;{0049810086} //Cambiar código de sellado, a su vez es el nombre del archivo\n"
    "#Operacion;19\n"
    "#Descripcion;{824903021361} //cambiar código de amortiguador\n"
)


def test_huella_plantilla_son_los_prefijos_de_los_campos_y_los_encabezados():
    plantilla = parsear_plantilla(_PLANTILLA_TXT, "txt")
    h = huellas.huella_plantilla(plantilla, ["sellado", "amortiguador"])
    assert h == {
        "campos": ["#Codigo;", "#Descripcion;"],
        "encabezados": ["amortiguador", "sellado"],
    }


def test_huella_plantilla_no_depende_del_numero_de_linea():
    # Una plantilla con una linea fija de mas arriba (#Operacion) antes de un
    # campo: el prefijo del campo es el mismo aunque cambie su numero de linea.
    otra = "#Nota;fija\n" + _PLANTILLA_TXT
    a = huellas.huella_plantilla(parsear_plantilla(_PLANTILLA_TXT, "txt"), ["sellado", "amortiguador"])
    b = huellas.huella_plantilla(parsear_plantilla(otra, "txt"), ["sellado", "amortiguador"])
    assert a == b


def test_plantilla_sin_campos_no_tiene_huella():
    assert huellas.huella_plantilla(parsear_plantilla("sin campos aca\n", "txt"), []) is None


def test_similitud_plantilla_de_la_misma_huella_es_uno():
    h = huellas.huella_plantilla(parsear_plantilla(_PLANTILLA_TXT, "txt"), ["sellado", "amortiguador"])
    assert huellas.similitud_plantilla(h, h) == 1.0


def test_similitud_plantilla_sin_nada_en_comun_es_cero():
    a = huellas.huella_plantilla(parsear_plantilla(_PLANTILLA_TXT, "txt"), ["sellado", "amortiguador"])
    otra = "#Otro;{x}\n"
    b = huellas.huella_plantilla(parsear_plantilla(otra, "txt"), ["area"])
    assert huellas.similitud_plantilla(a, b) == 0.0


# -- recetas por area -----------------------------------------------------------


def _ctx_recetas():
    catalogos = {
        _normalizar(area): cargar_catalogo(_RECETAS_DIR / carpeta, area)
        for area, carpeta in _AREAS.items()
    }
    encabezados, filas = leer_listado(_LISTADO_PATH.read_bytes(), _LISTADO_PATH.name)
    return construir_contexto(catalogos, encabezados, filas)


def test_huella_recetas_son_encabezados_normalizados_y_areas_presentes():
    h = huellas.huella_recetas(_ctx_recetas())
    assert h == {"encabezados": ["amortiguador", "area", "sellado"], "areas": ["gps2", "hd"]}


def test_similitud_recetas_de_la_misma_huella_es_uno():
    h = huellas.huella_recetas(_ctx_recetas())
    assert huellas.similitud_recetas(h, h) == 1.0


def test_similitud_recetas_sin_nada_en_comun_es_cero():
    a = huellas.huella_recetas(_ctx_recetas())
    b = {"encabezados": ["otra"], "areas": ["gps1"]}
    assert huellas.similitud_recetas(a, b) == 0.0
