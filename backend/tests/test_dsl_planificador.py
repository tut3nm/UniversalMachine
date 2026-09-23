"""
Tests del planificador con un LLM STUB (no el modelo real: eso queda para
pruebas manuales/lentas, ver PLAN_ASISTENTE_IA.md seccion 9). Lo que se
verifica aca es el WIRING: que un JSON de intencion valido se traduzca en el
Programa correcto, y que cualquier cosa no interpretable caiga en
'desconocido' en vez de adivinar.
"""
from pathlib import Path

from app.ai import llm
from app.ai.dsl.interprete import construir_contexto
from app.ai.dsl.planificador import planificar
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


def _stub(respuestas: list[str]):
    """Devuelve un ejecutor que responde cada llamada con el siguiente texto
    de la lista, en orden (una por etapa del planificador)."""
    respuestas = list(respuestas)

    def ejecutar(system, user, grammar=None, max_tokens=768):
        texto = respuestas.pop(0)
        return llm.LlmResult(True, texto)

    return ejecutar


def test_intencion_gruesa_sin_ajustes_finos_da_programa_de_una_operacion():
    stub = _stub([
        '{"operacion": "tabular_mediciones"}',
    ])
    programa = planificar("tabulame este archivo de mediciones", ctx_recetas=None, ejecutar_llm=stub)
    assert len(programa.operaciones) == 1
    assert programa.operaciones[0].op == "tabular_mediciones"


def test_intencion_desconocida_no_adivina():
    stub = _stub([
        '{"operacion": "desconocido"}',
    ])
    programa = planificar("hace algo con el archivo", ctx_recetas=None, ejecutar_llm=stub)
    assert programa.es_desconocido


def test_respuesta_no_json_cae_en_desconocido():
    stub = _stub(["esto no es json"])
    programa = planificar("cualquier cosa", ctx_recetas=None, ejecutar_llm=stub)
    assert programa.es_desconocido


def test_llm_no_disponible_cae_en_desconocido():
    def ejecutar(system, user, grammar=None, max_tokens=768):
        return llm.LlmResult(False, "", "IA local no disponible.")

    programa = planificar("generame las recetas por area", ctx_recetas=None, ejecutar_llm=ejecutar)
    assert programa.es_desconocido


def test_generar_recetas_por_area_con_ajuste_fino_del_ejemplo_del_plan():
    ctx = _ctx_recetas()
    stub = _stub([
        '{"operacion": "generar_recetas_por_area"}',
        (
            '[{"op": "filtrar_filas", "args": {"columna": "area", "valor": "HD"}},'
            ' {"op": "expandir_por_catalogo", "args": {"solo_sufijos": ["15", "17"]}},'
            ' {"op": "nombrar_archivo", "args": {"patron": "{amortiguador}.{sufijo}.def.txt"}}]'
        ),
    ])
    programa = planificar(
        "de este listado, genera solo las recetas .15 y .17 de las filas HD, "
        "y nombralas con el amortiguador en vez del sellado",
        ctx_recetas=ctx,
        ejecutar_llm=stub,
    )
    nombres_ops = [o.op for o in programa.operaciones]
    assert nombres_ops == ["filtrar_filas", "expandir_por_catalogo", "nombrar_archivo"]

    # el programa resultante es directamente ejecutable y valido
    from app.ai.dsl.interprete import ejecutar_programa
    resultado = ejecutar_programa(programa, ctx)
    assert len(resultado.archivos) == 24


def test_generar_recetas_por_area_sin_ajustes_agrega_expandir_por_defecto():
    ctx = _ctx_recetas()
    stub = _stub([
        '{"operacion": "generar_recetas_por_area"}',
        "[]",
    ])
    programa = planificar("generame las recetas por area de este listado", ctx_recetas=ctx, ejecutar_llm=stub)
    assert [o.op for o in programa.operaciones] == ["expandir_por_catalogo"]
