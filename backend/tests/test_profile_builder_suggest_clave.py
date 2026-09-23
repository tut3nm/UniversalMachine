"""
suggest_clave_row() migrado desde máquina232/src/profile_builder.py (mas
avanzado que la version que tenia backend/app/core hasta ahora): ver
PLAN_ASISTENTE_IA.md seccion 7. Sin este test, un futuro cambio podria
reintroducir la version simple sin que nada lo note.
"""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "app", "core"))

from profile_builder import suggest_clave_row  # noqa: E402


def test_prefiere_fila_de_texto_unica():
    grid = [
        ["1", "2", "3"],       # numerica, secuencia consecutiva: descartada
        ["A1", "A2", "A3"],    # texto, unica: candidata directa
    ]
    assert suggest_clave_row(grid, 0) == 1


def test_acepta_clave_numerica_como_respaldo_si_no_hay_texto():
    # caso real documentado: un codigo de pieza que resulta ser numerico
    # (RNROAMORTIGUADOR=4717012798) no deberia perder contra "no sugerir nada".
    grid = [
        ["10", "20", "30"],  # numerica, unica, NO consecutiva: candidata numerica
    ]
    assert suggest_clave_row(grid, 0) == 0


def test_secuencia_consecutiva_no_califica_como_clave():
    grid = [
        ["1", "2", "3", "4"],  # indice autogenerado: no es un codigo real
    ]
    assert suggest_clave_row(grid, 0) is None


def test_con_texto_y_numero_unicos_prefiere_texto():
    grid = [
        ["10", "20", "30"],     # numerica unica: candidata de respaldo
        ["A1", "A2", "A3"],     # texto unica: se prefiere siempre
    ]
    assert suggest_clave_row(grid, 0) == 1


def test_sin_fila_100_por_ciento_unica_usa_la_mas_casi_unica_como_ultimo_recurso():
    grid = [
        ["A", "A", "B"],        # 2/3 distintos
        ["X", "Y", "Y", "Z"],   # 3/4 distintos: mejor proporcion
    ]
    assert suggest_clave_row(grid, 0) == 1


def test_ninguna_fila_calificable_devuelve_none():
    grid = [["", "", ""]]
    assert suggest_clave_row(grid, 0) is None


def test_respeta_primera_col_para_ignorar_columnas_fijas():
    grid = [["etiqueta", "A1", "A2", "A3"]]
    assert suggest_clave_row(grid, 1) == 0
