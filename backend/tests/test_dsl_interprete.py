from pathlib import Path

import pytest

from app.ai.dsl.interprete import (
    Operacion,
    Programa,
    construir_contexto,
    ejecutar_programa,
    validar_programa,
)
from app.ai.plantillas_masivas import _normalizar, leer_listado
from app.ai.recetas_por_area import cargar_catalogo, generar_por_area

REPO_ROOT = Path(__file__).resolve().parents[2]
RECETAS_DIR = REPO_ROOT / "docs" / "Recetas"
LISTADO_PATH = REPO_ROOT / "docs" / "Recetas_Andon.txt"

_AREAS = {"HD": "RecetasHD", "GPS1": "RecetasGPS1", "GPS2": "RecetasGPS2"}


def _catalogos():
    return {
        _normalizar(area): cargar_catalogo(RECETAS_DIR / carpeta, area)
        for area, carpeta in _AREAS.items()
    }


def _listado_andon():
    return leer_listado(LISTADO_PATH.read_bytes(), LISTADO_PATH.name)


def test_programa_minimo_equivale_byte_a_byte_a_generar_por_area():
    catalogos = _catalogos()
    encabezados, filas = _listado_andon()

    esperado = generar_por_area(catalogos, encabezados, filas)

    ctx = construir_contexto(catalogos, encabezados, filas)
    programa = Programa(operaciones=(Operacion("expandir_por_catalogo", {}),))
    resultado = ejecutar_programa(programa, ctx)

    obtenidos = {a.nombre_archivo: a.contenido for a in resultado.archivos}
    esperados = {a.nombre_archivo: a.contenido for a in esperado.archivos}
    assert obtenidos == esperados
    assert len(resultado.archivos) == len(esperado.archivos) == 54


def test_ejemplo_del_plan_filtrar_expandir_reemplazar_nombrar():
    # PLAN_ASISTENTE_IA.md seccion 3.2: solo .15/.17 de las filas HD,
    # nombradas con el amortiguador en vez del sellado.
    catalogos = _catalogos()
    encabezados, filas = _listado_andon()
    ctx = construir_contexto(catalogos, encabezados, filas)

    programa = Programa(operaciones=(
        Operacion("filtrar_filas", {"columna": "area", "valor": "HD"}),
        Operacion("expandir_por_catalogo", {"solo_sufijos": ["15", "17"]}),
        Operacion("reemplazar_campo", {"campo": "#Codigo", "columna": "sellado"}),
        Operacion("reemplazar_campo", {"campo": "#Descripcion", "columna": "amortiguador"}),
        Operacion("nombrar_archivo", {"patron": "{amortiguador}.{sufijo}.def.txt"}),
    ))

    resultado = ejecutar_programa(programa, ctx)

    # 12 filas HD x 2 sufijos = 24
    assert len(resultado.archivos) == 24
    assert all(a.nombre_archivo.endswith((".15.def.txt", ".17.def.txt")) for a in resultado.archivos)
    # el nombre usa el amortiguador de la fila, no el sellado
    primera_fila_hd = next(f for f in filas if f["area"].strip() == "HD")
    esperado_amortiguador = primera_fila_hd["amortiguador"].strip()
    assert any(a.nombre_archivo.startswith(esperado_amortiguador) for a in resultado.archivos)


def test_quitar_comentarios_saca_las_lineas_de_nota():
    # Las plantillas de referencia reales (docs/Recetas/...) no tienen notas
    # '//' (esas son del mundo plantillas_masivas.py, no de este); se arma
    # una plantilla sintetica minima para probar la operacion igual.
    from app.ai.recetas_por_area import CatalogoArea, VarianteArea

    variante = VarianteArea(
        sufijo="15",
        lineas=[
            "// nota que no va al archivo final",
            "#Codigo;000",
            "#Descripcion;000",
        ],
        eol="\n",
        linea_codigo=1,
        linea_descripcion=2,
    )
    catalogos = {"hd": CatalogoArea(area="HD", variantes=[variante])}
    encabezados = ["sellado", "amortiguador", "area"]
    filas = [{"sellado": "111", "amortiguador": "222", "area": "HD"}]
    ctx = construir_contexto(catalogos, encabezados, filas)

    sin_quitar = ejecutar_programa(
        Programa(operaciones=(Operacion("expandir_por_catalogo", {}),)), ctx
    )
    con_quitar = ejecutar_programa(
        Programa(operaciones=(
            Operacion("expandir_por_catalogo", {}),
            Operacion("quitar_comentarios", {}),
        )),
        ctx,
    )

    assert any(l.strip().startswith("//") for l in sin_quitar.archivos[0].contenido.splitlines())
    assert not any(l.strip().startswith("//") for l in con_quitar.archivos[0].contenido.splitlines())
    assert len(con_quitar.archivos[0].contenido.splitlines()) == 2


def test_agrupar_salida_por_asigna_carpeta():
    catalogos = _catalogos()
    encabezados, filas = _listado_andon()
    ctx = construir_contexto(catalogos, encabezados, filas)

    programa = Programa(operaciones=(
        Operacion("expandir_por_catalogo", {}),
        Operacion("agrupar_salida_por", {"columna": "area"}),
    ))
    resultado = ejecutar_programa(programa, ctx)
    carpetas = {a.carpeta for a in resultado.archivos}
    assert carpetas == {"HD", "GPS2"}


def test_fila_con_area_desconocida_genera_advertencia_no_error():
    catalogos = {"hd": cargar_catalogo(RECETAS_DIR / "RecetasHD", "HD")}
    encabezados = ["sellado", "amortiguador", "area"]
    filas = [
        {"sellado": "111", "amortiguador": "AAA", "area": "HD"},
        {"sellado": "222", "amortiguador": "BBB", "area": "ZONA_INEXISTENTE"},
    ]
    ctx = construir_contexto(catalogos, encabezados, filas)
    resultado = ejecutar_programa(
        Programa(operaciones=(Operacion("expandir_por_catalogo", {}),)), ctx
    )
    assert len(resultado.advertencias) == 1
    assert "ZONA_INEXISTENTE" in resultado.advertencias[0]
    assert len(resultado.archivos) == 4  # solo la fila HD, que tiene 4 sufijos


def test_nombres_duplicados_agregan_sufijo_igual_que_generar_por_area():
    catalogos = {"hd": cargar_catalogo(RECETAS_DIR / "RecetasHD", "HD")}
    encabezados = ["sellado", "amortiguador", "area"]
    filas = [
        {"sellado": "X", "amortiguador": "A", "area": "HD"},
        {"sellado": "X", "amortiguador": "B", "area": "HD"},
    ]
    ctx = construir_contexto(catalogos, encabezados, filas)
    resultado = ejecutar_programa(
        Programa(operaciones=(Operacion("expandir_por_catalogo", {}),)), ctx
    )
    nombres = sorted(a.nombre_archivo for a in resultado.archivos)
    assert "X.15.def.txt" in nombres
    assert "X.15_2.def.txt" in nombres


# --- validacion: el contrato de seguridad de la seccion 3.4 del plan -------


def test_validar_rechaza_columna_inexistente_en_filtrar_filas():
    catalogos = _catalogos()
    encabezados, filas = _listado_andon()
    ctx = construir_contexto(catalogos, encabezados, filas)
    programa = Programa(operaciones=(
        Operacion("filtrar_filas", {"columna": "columna_que_no_existe", "valor": "x"}),
        Operacion("expandir_por_catalogo", {}),
    ))
    with pytest.raises(ValueError, match="columna_que_no_existe"):
        validar_programa(programa, ctx)


def test_validar_rechaza_sufijo_inexistente():
    catalogos = _catalogos()
    encabezados, filas = _listado_andon()
    ctx = construir_contexto(catalogos, encabezados, filas)
    programa = Programa(operaciones=(
        Operacion("expandir_por_catalogo", {"solo_sufijos": ["99"]}),
    ))
    with pytest.raises(ValueError, match="99"):
        validar_programa(programa, ctx)


def test_validar_rechaza_campo_invalido_en_reemplazar_campo():
    catalogos = _catalogos()
    encabezados, filas = _listado_andon()
    ctx = construir_contexto(catalogos, encabezados, filas)
    programa = Programa(operaciones=(
        Operacion("reemplazar_campo", {"campo": "#Inventado", "columna": "sellado"}),
        Operacion("expandir_por_catalogo", {}),
    ))
    with pytest.raises(ValueError, match="#Inventado"):
        validar_programa(programa, ctx)


def test_validar_rechaza_programa_sin_expandir():
    catalogos = _catalogos()
    encabezados, filas = _listado_andon()
    ctx = construir_contexto(catalogos, encabezados, filas)
    programa = Programa(operaciones=(Operacion("quitar_comentarios", {}),))
    with pytest.raises(ValueError, match="expandir_por_catalogo"):
        validar_programa(programa, ctx)


def test_validar_rechaza_operacion_inexistente():
    catalogos = _catalogos()
    encabezados, filas = _listado_andon()
    ctx = construir_contexto(catalogos, encabezados, filas)
    programa = Programa(operaciones=(Operacion("generar_recetas_por_area", {}),))
    with pytest.raises(ValueError, match="Operacion desconocida"):
        validar_programa(programa, ctx)


def test_validar_rechaza_operacion_de_otra_pantalla():
    catalogos = _catalogos()
    encabezados, filas = _listado_andon()
    ctx = construir_contexto(catalogos, encabezados, filas)
    programa = Programa(operaciones=(Operacion("definir_tablas", {"tablas": []}),))
    with pytest.raises(ValueError, match="no es una operacion de recetas"):
        validar_programa(programa, ctx)


@pytest.mark.parametrize("patron, mensaje", [
    ("HD.*.15.*.17.*", "caracteres invalidos"),
    ("{sellado}.def.txt", "tiene que incluir {sufijo}"),
    ("{sufijo}.def.txt", "tiene que incluir una columna"),
    ("{inventado}.{sufijo}.def.txt", "slot inexistente"),
    ("", "falta el patron"),
])
def test_validar_rechaza_patrones_de_nombre_invalidos(patron, mensaje):
    # 'HD.*.15.*.17.*' es lo que emitio el modelo real antes de restringir
    # el patron en la gramatica: 54 archivos con un nombre invalido en Windows.
    ctx = construir_contexto(_catalogos(), *_listado_andon())
    programa = Programa(operaciones=(
        Operacion("expandir_por_catalogo", {}),
        Operacion("nombrar_archivo", {"patron": patron}),
    ))
    with pytest.raises(ValueError, match=mensaje):
        validar_programa(programa, ctx)
