"""Clasificacion listado/tabla al ejecutar un programa de mediciones. Ver
PLAN_MEMORIA_FORMATOS.md, seccion 5.1: el modelo clasifica por rango, y un
rango sin 'tipo' (el modelo no respondio, o no lo incluyo) cae al respaldo
determinista: clave/valor -> listado, el resto -> tabla."""
from app.ai.dsl.interprete import Operacion, Programa
from app.ai.dsl import interprete_mediciones as im

_LINEAS = [
    "Codigo,001",
    "Fecha,2026-09-23",
    "",
    "Nombre,Edad,Ciudad",
    "Ana,30,Rosario",
    "Beto,40,Cordoba",
]


def _programa(tablas):
    return Programa(operaciones=(
        Operacion("usar_separador", {"separador": ","}),
        Operacion("definir_tablas", {"tablas": tablas}),
    ))


def test_tipo_explicito_del_modelo_se_respeta():
    resultado = im.ejecutar(_programa([{"desde": 4, "hasta": 6, "tipo": "listado"}]), _LINEAS)
    assert resultado.tablas[0].con_encabezado is False


def test_sin_tipo_cae_al_respaldo_clave_valor():
    resultado = im.ejecutar(_programa([{"desde": 1, "hasta": 2, "tipo": None}]), _LINEAS)
    assert resultado.tablas[0].con_encabezado is False


def test_sin_tipo_cae_al_respaldo_tabla():
    resultado = im.ejecutar(_programa([{"desde": 4, "hasta": 6}]), _LINEAS)
    assert resultado.tablas[0].con_encabezado is True
