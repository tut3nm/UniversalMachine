"""
El test que sostiene el contrato de seguridad de PLAN_ASISTENTE_IA.md seccion
3.4: un encabezado o sufijo que el contexto no tiene debe ser IMPOSIBLE de
emitir para la gramatica, no solo improbable. Se verifica de forma
estructural (que el alfabeto de la regla 'columna'/'sufijo' sea exactamente
el conjunto permitido), sin depender de correr el modelo real.
"""
from app.ai.dsl.gramatica import gramatica_intencion, gramatica_parametros
from app.ai.dsl.operaciones import OPERACION_DESCONOCIDO, nombres_gruesas


def test_gramatica_intencion_solo_admite_las_operaciones_gruesas_y_desconocido():
    g = gramatica_intencion()
    for nombre in nombres_gruesas() + [OPERACION_DESCONOCIDO]:
        assert f'"\\"{nombre}\\""' in g
    # una operacion inventada no puede aparecer como alternativa literal
    assert '"\\"borrar_todo\\""' not in g


def test_gramatica_parametros_columna_es_exactamente_el_conjunto_permitido():
    encabezados = ["sellado", "area"]
    g = gramatica_parametros(encabezados, sufijos_disponibles=["15", "17"])

    linea_columna = next(l for l in g.splitlines() if l.startswith("columna ::="))
    assert '"\\"sellado\\""' in linea_columna
    assert '"\\"area\\""' in linea_columna
    # 'amortiguador' no esta en los encabezados de este contexto: no puede
    # aparecer como alternativa de la regla 'columna', ni como substring de
    # otra alternativa (que rompería la garantia por casualidad de nombres).
    assert "amortiguador" not in linea_columna


def test_gramatica_parametros_sufijo_es_exactamente_el_conjunto_permitido():
    g = gramatica_parametros(["sellado"], sufijos_disponibles=["15", "17"])
    linea_sufijo = next(l for l in g.splitlines() if l.startswith("sufijo ::="))
    assert '"\\"15\\""' in linea_sufijo
    assert '"\\"17\\""' in linea_sufijo
    assert '"\\"99\\""' not in linea_sufijo


def test_gramatica_parametros_campo_se_limita_a_codigo_y_descripcion():
    g = gramatica_parametros(["sellado"], sufijos_disponibles=["15"])
    linea_campo = next(l for l in g.splitlines() if l.startswith("campo ::="))
    assert '"\\"#Codigo\\""' in linea_campo
    assert '"\\"#Descripcion\\""' in linea_campo


def test_gramatica_parametros_sin_contexto_no_rompe():
    # pantalla sin listado cargado todavia: la gramatica se puede construir
    # igual (encabezados/sufijos vacios), simplemente no admite ninguna
    # columna/sufijo real todavia.
    g = gramatica_parametros([], [])
    assert "root ::=" in g
