"""
El test que sostiene el contrato de seguridad de PLAN_ASISTENTE_IA.md seccion
3.4 (y 12): un encabezado, sufijo, valor, linea de plantilla o separador que
el contexto no tiene - o que el mensaje del usuario no menciona - debe ser
IMPOSIBLE de emitir para la gramatica, no solo improbable. Se verifica de
forma estructural, sin depender de correr el modelo real.
"""
import re

import pytest

from app.ai.dsl.gramatica import gramatica_mediciones, gramatica_plantilla, gramatica_recetas


def _regla(g: str, nombre: str) -> str:
    return next(l for l in g.splitlines() if l.startswith(f"{nombre} ::="))


def _tiene_regla(g: str, nombre: str) -> bool:
    return any(l.startswith(f"{nombre} ::=") for l in g.splitlines())


def _recetas(columnas=(), sufijos=(), valores=None, campos=(), quitar=False, agrupar=True, nombrar=True):
    columnas = list(columnas)
    return gramatica_recetas(
        columnas, list(sufijos), valores or {}, columnas, list(campos), quitar, agrupar, nombrar
    )


@pytest.mark.parametrize("g", [
    _recetas(["sellado", "area"], ["15", "17"], {"area": ["HD"]}, ["#Codigo"], True),
    _recetas(),
    _recetas(sufijos=["15"]),
    gramatica_mediciones([(1, 12)]),
    gramatica_mediciones([]),
    gramatica_plantilla([1], ["sellado", "area"], {"area": ["HD"]}, True),
    gramatica_plantilla([], [], {}, False),
])
def test_nombres_de_regla_validos_para_llama_cpp(g):
    # El parser GBNF de llama.cpp solo acepta [a-zA-Z0-9-] en los nombres de
    # regla: con un '_' la gramatica entera falla ("failed to parse grammar")
    # y el asistente cae en silencio al default. Los tests con modelo stub no
    # lo ven, por eso se fija aca.
    nombres = [l.split(" ::= ", 1)[0] for l in g.splitlines() if " ::= " in l]
    assert nombres
    assert all(re.fullmatch(r"[a-zA-Z0-9-]+", n) for n in nombres), nombres


# -- recetas ------------------------------------------------------------------


def test_recetas_sin_menciones_solo_admite_lista_vacia():
    # expandir todo es el default que agrega el planificador: sin nada
    # mencionado no hay ninguna operacion que el modelo pueda emitir.
    assert _recetas() == 'root ::= "[]"\n'


def test_recetas_expandir_a_lo_sumo_una_vez_y_primera():
    g = _recetas(["area"], sufijos=["15", "17"])
    assert _regla(g, "root").startswith('root ::= "[" op-expandir ("," operacion)')
    assert "op-expandir" not in _regla(g, "operacion")


def test_recetas_agrupar_y_nombrar_solo_si_se_piden():
    g = _recetas(["area"], agrupar=False, nombrar=False)
    assert not _tiene_regla(g, "op-agrupar")
    assert not _tiene_regla(g, "op-nombrar")


def test_recetas_columna_es_exactamente_lo_mencionado():
    linea_columna = _regla(_recetas(["sellado", "area"]), "columna")
    assert '"\\"sellado\\""' in linea_columna
    assert '"\\"area\\""' in linea_columna
    assert "amortiguador" not in linea_columna


def test_recetas_sufijo_es_exactamente_lo_mencionado():
    g = _recetas(sufijos=["15", "17"])
    assert _regla(g, "root") == 'root ::= "[" op-expandir "]"'
    assert _regla(g, "sufijo") == 'sufijo ::= "\\"15\\"" | "\\"17\\""'


def test_recetas_reemplazar_campo_necesita_campo_y_columna_mencionados():
    assert not _tiene_regla(_recetas(["sellado"]), "op-reemplazar")
    g = _recetas(["sellado"], campos=["#Descripcion"])
    assert _regla(g, "campo") == 'campo ::= "\\"#Descripcion\\""'


def test_recetas_quitar_comentarios_solo_si_se_pide():
    assert "quitar_comentarios" not in _recetas()
    assert "quitar_comentarios" in _recetas(quitar=True)


def test_filtro_solo_admite_valores_que_la_columna_tiene():
    g = _recetas(valores={"area": ["HD", "GPS2", "HD", " "], "sellado": []})
    assert _regla(g, "valor-0") == 'valor-0 ::= "\\"GPS2\\"" | "\\"HD\\""'
    # 'sellado' no tiene valores mencionados: no se ofrece para filtrar
    assert '\\"sellado\\"' not in _regla(g, "op-filtrar")


def test_patron_de_nombre_son_columnas_mencionadas_sufijo_y_extension():
    g = _recetas(["amortiguador"])
    assert _regla(g, "patron") == (
        'patron ::= "\\"" (slot-nombre separador-nombre){1,3} "{sufijo}.def.txt\\""'
    )
    assert _regla(g, "slot-nombre") == 'slot-nombre ::= "{amortiguador}"'


# -- mediciones ---------------------------------------------------------------


def test_mediciones_solo_admite_sus_dos_operaciones():
    g = gramatica_mediciones([(1, 12), (14, 212)])
    assert _regla(g, "operacion") == "operacion ::= op-tablas | op-separador"
    assert "filtrar_filas" not in g
    assert "asignar_columna" not in g


def test_mediciones_separador_es_la_lista_cerrada():
    linea = _regla(gramatica_mediciones([(1, 1)]), "separador")
    alternativas = [a.strip() for a in linea.split("::=", 1)[1].split(" | ")]
    assert alternativas == ['"\\",\\""', '"\\";\\""', '"\\"\\\\t\\""', '"\\"|\\""']


def test_mediciones_tablas_solo_los_rangos_que_escribio_el_usuario():
    g = gramatica_mediciones([(14, 212), (1, 12)])
    assert _regla(g, "tabla") == (
        'tabla ::= "{\\"desde\\": 14, \\"hasta\\": 212, \\"tipo\\": " tipo "}" | '
        '"{\\"desde\\": 1, \\"hasta\\": 12, \\"tipo\\": " tipo "}"'
    )
    assert _regla(g, "tipo") == 'tipo ::= "\\"tabla\\"" | "\\"listado\\""'


def test_mediciones_sin_rangos_en_el_mensaje_no_puede_definir_tablas():
    g = gramatica_mediciones([])
    assert _regla(g, "operacion") == "operacion ::= op-separador"
    assert "definir_tablas" not in g


# -- plantilla ----------------------------------------------------------------


def test_plantilla_linea_y_columna_son_exactamente_lo_mencionado():
    g = gramatica_plantilla([1, 3], ["sellado", "Código"], {}, False)
    assert _regla(g, "linea") == 'linea ::= "1" | "3"'
    assert _regla(g, "columna") == 'columna ::= "\\"sellado\\"" | "\\"Código\\""'
    assert "nombre_archivo_desde" not in g


def test_plantilla_nombre_de_archivo_solo_si_se_habla_del_nombre():
    g = gramatica_plantilla([], ["amortiguador"], {}, True)
    assert _regla(g, "operacion") == "operacion ::= op-nombre"


def test_plantilla_sin_menciones_solo_admite_lista_vacia():
    assert gramatica_plantilla([], [], {}, False) == 'root ::= "[]"\n'
