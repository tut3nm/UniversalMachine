import pytest
from pathlib import Path

from app.ai import tablas_delimitadas as td
from app.ai.dsl.interprete import Operacion, construir_contexto
from app.ai.memoria import anclaje
from app.ai.plantillas_masivas import _normalizar, leer_listado, parsear_plantilla
from app.ai.recetas_por_area import cargar_catalogo

DOCS = Path(__file__).resolve().parents[2] / "docs" / "H1312"
_RECETAS_DIR = Path(__file__).resolve().parents[2] / "docs" / "Recetas"
_LISTADO_PATH = Path(__file__).resolve().parents[2] / "docs" / "Recetas_Andon.txt"
_AREAS = {"HD": "RecetasHD", "GPS1": "RecetasGPS1", "GPS2": "RecetasGPS2"}


def _lineas(nombre: str) -> list[str]:
    return td.decodificar((DOCS / nombre).read_bytes())


def _tablas_confirmadas(lineas: list[str], sep: str) -> list[dict]:
    """Lo que el usuario confirmo: los bloques que detecta el motor,
    traducidos a la forma {desde, hasta, tipo} del programa DSL."""
    return [
        {"desde": d.desde, "hasta": d.hasta, "tipo": "tabla" if d.con_encabezado else "listado"}
        for d in td.detectar_tablas(lineas, sep)
    ]


def test_anclar_y_aplicar_a_otro_archivo_del_mismo_formato():
    lineas_005 = _lineas("824902015333_280826_005.csv")
    sep = td.detectar_separador(lineas_005)
    regla = anclaje.anclar_mediciones(_tablas_confirmadas(lineas_005, sep), sep, lineas_005)

    lineas_021224 = _lineas("824902015333_021224_000.csv")
    tablas = anclaje.aplicar_mediciones(regla, lineas_021224)

    # mismas tablas (mismos titulos y tipos) que la deteccion automatica de
    # ese otro archivo, aunque los numeros de fila sean distintos.
    esperado = _tablas_confirmadas(lineas_021224, sep)
    assert [t["tipo"] for t in tablas] == [t["tipo"] for t in esperado]
    assert [(t["desde"], t["hasta"]) for t in tablas] == [(d["desde"], d["hasta"]) for d in esperado]


def test_regla_a_json_y_de_vuelta_es_identica():
    lineas = _lineas("824902015333_280826_005.csv")
    sep = td.detectar_separador(lineas)
    regla = anclaje.anclar_mediciones(_tablas_confirmadas(lineas, sep), sep, lineas)
    assert anclaje.regla_desde_json(anclaje.regla_a_json(regla)) == regla


def test_ancla_ausente_es_un_error_explicito():
    regla = anclaje.ReglaMediciones(
        separador=",",
        tablas=(anclaje.TablaAnclada("[No existe esta seccion]", "linea vacia", "tabla"),),
    )
    lineas = _lineas("824902015333_280826_005.csv")
    with pytest.raises(ValueError, match="No encontre"):
        anclaje.aplicar_mediciones(regla, lineas)


def test_ancla_inicio_de_archivo_y_fin_de_archivo():
    lineas = ["a,b,c", "1,2,3", "4,5,6"]
    regla = anclaje.anclar_mediciones(
        [{"desde": 1, "hasta": 3, "tipo": "tabla"}], ",", lineas
    )
    assert regla.tablas[0].ancla_desde == anclaje.ANCLA_INICIO
    assert regla.tablas[0].ancla_hasta == anclaje.ANCLA_FIN


# -- plantilla (PLAN_MEMORIA_FORMATOS.md, 5.2) ---------------------------------

_PLANTILLA_TXT = (
    "#Codigo;{0049810086} //Cambiar código de sellado, a su vez es el nombre del archivo\n"
    "#Operacion;19\n"
    "#Descripcion;{824903021361} //cambiar código de amortiguador\n"
)


def test_anclar_plantilla_por_prefijo_no_por_linea():
    plantilla = parsear_plantilla(_PLANTILLA_TXT, "txt")
    regla = anclaje.anclar_plantilla(
        [{"linea": 1, "columna": "sellado"}, {"linea": 3, "columna": "amortiguador"}],
        "sellado", plantilla,
    )
    assert set(regla.asignaciones) == {
        anclaje.AsignacionAnclada("#Codigo;", "sellado"),
        anclaje.AsignacionAnclada("#Descripcion;", "amortiguador"),
    }
    assert regla.columna_nombre_archivo == "sellado"


def test_aplicar_plantilla_resuelve_la_nueva_linea_de_cada_campo():
    original = parsear_plantilla(_PLANTILLA_TXT, "txt")
    regla = anclaje.anclar_plantilla(
        [{"linea": 1, "columna": "sellado"}, {"linea": 3, "columna": "amortiguador"}],
        "sellado", original,
    )
    # otra plantilla del mismo formato, con una linea fija de mas arriba: los
    # campos quedan corridos, pero los prefijos son los mismos.
    otra = parsear_plantilla("#Nota;fija\n" + _PLANTILLA_TXT, "txt")
    asignaciones, columna_nombre = anclaje.aplicar_plantilla(
        regla, otra, ["sellado", "amortiguador"]
    )
    assert {(a["linea"], a["columna"]) for a in asignaciones} == {(2, "sellado"), (4, "amortiguador")}
    assert columna_nombre == "sellado"


def test_aplicar_plantilla_campo_ausente_es_un_error_explicito():
    original = parsear_plantilla(_PLANTILLA_TXT, "txt")
    regla = anclaje.anclar_plantilla([{"linea": 1, "columna": "sellado"}], None, original)
    otra = parsear_plantilla("#Otro;{x}\n", "txt")
    with pytest.raises(ValueError, match="No encontre"):
        anclaje.aplicar_plantilla(regla, otra, ["sellado"])


def test_aplicar_plantilla_columna_ausente_en_el_listado_es_un_error():
    original = parsear_plantilla(_PLANTILLA_TXT, "txt")
    regla = anclaje.anclar_plantilla([{"linea": 1, "columna": "sellado"}], None, original)
    with pytest.raises(ValueError, match="no tiene la columna"):
        anclaje.aplicar_plantilla(regla, original, ["otra_columna"])


def test_regla_plantilla_a_json_y_de_vuelta_es_identica():
    plantilla = parsear_plantilla(_PLANTILLA_TXT, "txt")
    regla = anclaje.anclar_plantilla([{"linea": 1, "columna": "sellado"}], "sellado", plantilla)
    assert anclaje.regla_plantilla_desde_json(anclaje.regla_plantilla_a_json(regla)) == regla


# -- recetas por area (PLAN_MEMORIA_FORMATOS.md, 5.3) --------------------------


def _ctx_recetas():
    catalogos = {
        _normalizar(area): cargar_catalogo(_RECETAS_DIR / carpeta, area)
        for area, carpeta in _AREAS.items()
    }
    encabezados, filas = leer_listado(_LISTADO_PATH.read_bytes(), _LISTADO_PATH.name)
    return construir_contexto(catalogos, encabezados, filas)


def test_anclar_recetas_descarta_filtrar_filas_y_solo_sufijos_de_expandir():
    operaciones = [
        Operacion("filtrar_filas", {"columna": "area", "valor": "HD"}),
        Operacion("expandir_por_catalogo", {"solo_sufijos": ["15", "17"]}),
        Operacion("nombrar_archivo", {"patron": "{amortiguador}.{sufijo}.def.txt"}),
    ]
    regla = anclaje.anclar_recetas(operaciones)
    assert [o.op for o in regla.operaciones] == ["nombrar_archivo"]


def test_aplicar_recetas_agrega_expandir_sin_restriccion_de_sufijos():
    regla = anclaje.anclar_recetas([
        Operacion("nombrar_archivo", {"patron": "{amortiguador}.{sufijo}.def.txt"}),
    ])
    programa = anclaje.aplicar_recetas(regla, _ctx_recetas())
    assert [o.op for o in programa.operaciones] == ["expandir_por_catalogo", "nombrar_archivo"]
    assert programa.operaciones[0].args == {}


def test_aplicar_recetas_columna_ausente_es_un_error_explicito():
    regla = anclaje.anclar_recetas([
        Operacion("reemplazar_campo", {"campo": "#Codigo", "columna": "no_existe"}),
    ])
    with pytest.raises(ValueError, match="no existe en el listado"):
        anclaje.aplicar_recetas(regla, _ctx_recetas())


def test_regla_recetas_a_json_y_de_vuelta_es_identica():
    regla = anclaje.anclar_recetas([
        Operacion("agrupar_salida_por", {"columna": "area"}),
        Operacion("quitar_comentarios", {}),
    ])
    assert anclaje.regla_recetas_desde_json(anclaje.regla_recetas_a_json(regla)) == regla
