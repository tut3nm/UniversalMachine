from pathlib import Path

import pytest

from app.ai.plantillas_masivas import generar, leer_listado, parsear_plantilla

REPO_ROOT = Path(__file__).resolve().parents[2]
PLANTILLA_PATH = REPO_ROOT / "docs" / "Recetas" / "plantilla.txt"
LISTADO_PATH = REPO_ROOT / "docs" / "Recetas_Andon.txt"


def test_caso_base_genera_un_archivo_por_fila():
    texto = PLANTILLA_PATH.read_text(encoding="utf-8")
    plantilla = parsear_plantilla(texto, extension="txt")
    encabezados, filas = leer_listado(LISTADO_PATH.read_bytes(), LISTADO_PATH.name)

    assert encabezados == ["amortiguador", "sellado", "area"]
    assert len(filas) == 14

    resultado = generar(plantilla, encabezados, filas)

    assert len(resultado.archivos) == 14
    assert resultado.columnas_sin_uso == ["area"]
    # ninguna linea de la plantilla queda sin match (la leyenda "* #Maquina..."
    # no tiene "{...}", asi que ni siquiera se considera un campo variable)
    assert resultado.lineas_ignoradas == []

    primero = resultado.archivos[0]
    assert primero.nombre_archivo == "001789002162.txt"
    assert "#Codigo;001789002162" in primero.contenido
    assert "#Descripcion;301700019344" in primero.contenido
    assert "#Operacion;19" in primero.contenido
    # la leyenda con "<...>" no se toca (queda completa en el archivo final)
    assert "* #Maquina;<idMaquinas>;<default>;<GPH>;<TEP>;<MUL>;<DIV>" in primero.contenido
    assert "#Maquina;1200009;True;;19.40;1;1" in primero.contenido
    # las notas "// ..." no quedan en el archivo final
    assert "//" not in primero.contenido


def test_nombres_duplicados_agregan_sufijo():
    plantilla = parsear_plantilla(
        "#Codigo;{ABC} //sellado, nombre del archivo\n",
        extension="txt",
    )
    encabezados = ["sellado"]
    filas = [{"sellado": "X"}, {"sellado": "X"}, {"sellado": "X"}]

    resultado = generar(plantilla, encabezados, filas)

    nombres = [a.nombre_archivo for a in resultado.archivos]
    assert nombres == ["X.txt", "X_2.txt", "X_3.txt"]


def test_comentario_sin_columna_reconocible_se_ignora():
    plantilla = parsear_plantilla(
        "#Codigo;{ABC} //sellado, nombre del archivo\n"
        "#Extra;{999} //no menciona ninguna columna conocida\n",
        extension="txt",
    )
    encabezados = ["sellado"]
    filas = [{"sellado": "X"}]

    resultado = generar(plantilla, encabezados, filas)

    assert resultado.lineas_ignoradas == [1]
    # las notas se eliminan, matcheen o no columna; el valor de la linea
    # ignorada queda igual al de la plantilla (sin llaves)
    assert resultado.archivos[0].contenido == "#Codigo;X\n#Extra;999"


def test_comentario_con_dos_columnas_reconocibles_se_ignora():
    plantilla = parsear_plantilla(
        "#Codigo;{ABC} //sellado, nombre del archivo\n"
        "#Ambiguo;{999} //podria ser sellado o area\n",
        extension="txt",
    )
    encabezados = ["sellado", "area"]
    filas = [{"sellado": "X", "area": "Y"}]

    resultado = generar(plantilla, encabezados, filas)

    assert resultado.lineas_ignoradas == [1]
    assert "#Ambiguo;999" in resultado.archivos[0].contenido


def test_dos_filas_generan_mismo_nombre_via_columnas_distintas_de_encabezado():
    # cubre el caso de que "sellado" con acentos en el encabezado matchee
    # un comentario sin acentos y viceversa
    plantilla = parsear_plantilla(
        "#Codigo;{ABC} //código de sellado, nombre del archivo\n",
        extension="txt",
    )
    encabezados = ["Sellado"]
    filas = [{"Sellado": "X"}]

    resultado = generar(plantilla, encabezados, filas)

    assert resultado.archivos[0].nombre_archivo == "X.txt"


def test_falta_fila_con_menos_columnas_que_encabezado_lanza_error():
    contenido = b"amortiguador;sellado;area\n1;2;3\n1;2\n"
    with pytest.raises(ValueError):
        leer_listado(contenido, "listado.csv")


def test_sin_campo_nombre_archivo_lanza_error():
    plantilla = parsear_plantilla("#Codigo;{ABC} //sellado\n", extension="txt")
    with pytest.raises(ValueError):
        generar(plantilla, ["sellado"], [{"sellado": "X"}])


def test_xlsx_no_soportado_en_v1():
    with pytest.raises(ValueError):
        leer_listado(b"", "listado.xlsx")
