"""
Tests del planificador con un LLM STUB (no el modelo real: eso queda para
pruebas manuales/lentas, ver PLAN_ASISTENTE_IA.md seccion 9). Lo que se
verifica aca es el WIRING: que el JSON que emite el modelo se traduzca en las
operaciones de la pantalla, y que una respuesta no interpretable no se
adivine: queda marcada como 'la IA no respondio'.
"""
from pathlib import Path

from app.ai import llm
from app.ai.dsl.interprete import construir_contexto, ejecutar_programa, Programa
from app.ai.dsl.planificador import (
    columnas_mencionadas,
    lineas_mencionadas,
    rangos_mencionados,
    sufijos_mencionados,
    valores_mencionados,
    planificar_mediciones,
    planificar_plantilla,
    planificar_recetas,
)
from app.ai.plantillas_masivas import _normalizar, leer_listado
from app.ai.recetas_por_area import cargar_catalogo

REPO_ROOT = Path(__file__).resolve().parents[2]
RECETAS_DIR = REPO_ROOT / "docs" / "Recetas"
LISTADO_PATH = REPO_ROOT / "docs" / "Recetas_Andon.txt"
_AREAS = {"HD": "RecetasHD", "GPS1": "RecetasGPS1", "GPS2": "RecetasGPS2"}


def _ctx_recetas():
    catalogos = {
        _normalizar(area): cargar_catalogo(RECETAS_DIR / carpeta, area)
        for area, carpeta in _AREAS.items()
    }
    encabezados, filas = leer_listado(LISTADO_PATH.read_bytes(), LISTADO_PATH.name)
    return construir_contexto(catalogos, encabezados, filas)


def _stub(respuesta: str, llamadas: list | None = None):
    def ejecutar(system, user, grammar=None, max_tokens=768):
        if llamadas is not None:
            llamadas.append({"system": system, "user": user, "grammar": grammar})
        return llm.LlmResult(True, respuesta)

    return ejecutar


def _llm_caido(system, user, grammar=None, max_tokens=768):
    return llm.LlmResult(False, "", "IA local no disponible.")


def test_recetas_con_ajuste_fino_del_ejemplo_del_plan():
    ctx = _ctx_recetas()
    stub = _stub(
        '[{"op": "filtrar_filas", "args": {"columna": "area", "valor": "HD"}},'
        ' {"op": "expandir_por_catalogo", "args": {"solo_sufijos": ["15", "17"]}},'
        ' {"op": "nombrar_archivo", "args": {"patron": "{amortiguador}.{sufijo}.def.txt"}}]'
    )
    plan = planificar_recetas(
        "de este listado, genera solo las recetas .15 y .17 de las filas HD, "
        "y nombralas con el amortiguador en vez del sellado",
        ctx, ejecutar_llm=stub,
    )
    assert plan.ia_respondio
    assert [o.op for o in plan.operaciones] == ["filtrar_filas", "expandir_por_catalogo", "nombrar_archivo"]
    resultado = ejecutar_programa(Programa(operaciones=plan.operaciones), ctx)
    assert len(resultado.archivos) == 24


def test_recetas_sin_ajustes_agrega_expandir_por_defecto():
    plan = planificar_recetas("generame las recetas de este listado", _ctx_recetas(), ejecutar_llm=_stub("[]"))
    assert [o.op for o in plan.operaciones] == ["expandir_por_catalogo"]
    assert plan.ia_respondio


def test_recetas_llm_caido_sigue_con_el_default_y_lo_marca():
    plan = planificar_recetas("lo que sea", _ctx_recetas(), ejecutar_llm=_llm_caido)
    assert [o.op for o in plan.operaciones] == ["expandir_por_catalogo"]
    assert plan.ia_respondio is False


def test_respuesta_no_json_se_marca_como_ia_no_respondio():
    lineas = [f"linea {n}" for n in range(1, 11)]
    plan = planificar_mediciones("cualquier cosa", lineas, "nada", ejecutar_llm=_stub("esto no es json"))
    assert plan.operaciones == ()
    assert plan.ia_respondio is False


def test_mediciones_usa_su_gramatica_y_le_da_contexto_al_modelo():
    llamadas: list = []
    stub = _stub(
        '[{"op": "definir_tablas", "args": {"tablas": ['
        '{"desde": 1, "hasta": 12, "tipo": "tabla"},'
        ' {"desde": 14, "hasta": 212, "tipo": "tabla"}]}}]',
        llamadas,
    )
    lineas = [f"a,b,c" for _ in range(212)]
    plan = planificar_mediciones(
        "De la fila 1 a la 12 es la primera tabla y de la 14 a la 212 la otra",
        lineas, "separador ','; tablas en filas 2-11, filas 14-212", ejecutar_llm=stub,
    )
    assert [o.op for o in plan.operaciones] == ["definir_tablas"]
    assert plan.operaciones[0].args["tablas"][1] == {"desde": 14, "hasta": 212, "tipo": "tabla"}
    assert "212 filas" in llamadas[0]["system"]
    assert "definir_tablas" in llamadas[0]["grammar"]
    assert "asignar_columna" not in llamadas[0]["grammar"]


def test_plantilla_traduce_asignaciones_de_columna():
    llamadas: list = []
    stub = _stub(
        '[{"op": "asignar_columna", "args": {"linea": 3, "columna": "sellado"}},'
        ' {"op": "nombre_archivo_desde", "args": {"columna": "amortiguador"}}]',
        llamadas,
    )
    plan = planificar_plantilla(
        "la descripcion sale del sellado y el nombre del archivo del amortiguador",
        [(1, "#Codigo;{0049810086}"), (3, "#Descripcion;{824903021361}")],
        ["amortiguador", "sellado", "area"],
        [{"amortiguador": "1", "sellado": "2", "area": "HD"}],
        ejecutar_llm=stub,
    )
    assert [o.op for o in plan.operaciones] == ["asignar_columna", "nombre_archivo_desde"]
    assert "linea 3: #Descripcion;{824903021361}" in llamadas[0]["system"]


def test_rangos_mencionados_lee_pares_a_y_filas_sueltas_en_orden():
    texto = "de la fila 1 a la 12, y de la 14 a 212; ignorar el 0 y el 999"
    assert rangos_mencionados(texto, 212) == [(1, 12), (14, 212)]


def test_rangos_mencionados_filas_sueltas_dan_un_rango_de_una_fila():
    texto = "la fila 56 y 57 son datos aislados"
    assert rangos_mencionados(texto, 212) == [(56, 56), (57, 57)]


def test_rangos_mencionados_ignora_numeros_fuera_del_archivo():
    texto = "de la fila 1 a la 999"
    assert rangos_mencionados(texto, 212) == []


def test_valores_mencionados_solo_los_que_nombra_el_mensaje():
    filas = [
        {"sellado": "001789002162", "area": "GPS2"},
        {"sellado": "001789002361", "area": "HD"},
    ]
    assert valores_mencionados("solo las filas gps2", ["sellado", "area"], filas) == {
        "sellado": [], "area": ["GPS2"],
    }
    # 'HD' no esta como palabra suelta dentro de 'HDMI'
    assert valores_mencionados("el cable HDMI", ["area"], filas) == {"area": []}


def test_sufijos_mencionados():
    assert sufijos_mencionados("solo las recetas .15 y .17", ["15", "17", "19", "20"]) == ["15", "17"]


def test_lineas_de_plantilla_mencionadas_por_sus_palabras():
    lineas = [(1, "#Codigo;{0049810086}"), (3, "#Descripcion;{824903021361}")]
    assert lineas_mencionadas("el código lo llena el amortiguador", lineas) == [1]
    assert lineas_mencionadas("la descripcion sale del sellado", lineas) == [3]
    # el valor entre llaves no cuenta como palabra de la linea
    assert lineas_mencionadas("el 0049810086", lineas) == []
    assert lineas_mencionadas("la línea 3 la llena el sellado", lineas) == [3]


def test_columnas_mencionadas_sin_acentos_ni_mayusculas():
    assert columnas_mencionadas("agrupá por Área", ["sellado", "area"]) == ["area"]
