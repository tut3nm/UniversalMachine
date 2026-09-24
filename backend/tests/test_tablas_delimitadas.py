import io
from pathlib import Path

import openpyxl
import pytest

from app.ai import tablas_delimitadas as td

DOCS = Path(__file__).resolve().parents[2] / "docs"

# Misma forma que docs/H1312/824902015333_280826_006.csv (el archivo del pedido
# del 2026-09-23): titulo, encabezado de 8 nombres con filas de 12 valores,
# titulo de la segunda tabla, linea vacia, encabezado y filas con coma final.
CSV_DOS_TABLAS = "\r\n".join([
    "[Messprogrammseite 1]",
    "Zyklen,Hub,Mittelpos,Geschw,ZugOG-A1,ZugUG-A1,DruckOG-A1,DruckUG-A1",
    "2,75,1335,0.262,0,0,0,0,4621242,4613528,4200380,4580856",
    "1,50,1330,0.050,320,210,760,570,4621242,4613528,4200380,4580856",
    "# QSStat",
    "",
    "Datum,Uhrzeit,Achse,Bewertung,Nummer,ZugV1,DruckV1",
    "28.08.26,04:37:28,A1,IO,1,1994,   0,",
    "28.08.26,04:38:41,A1,NIO,2,2076,1586,",
])

CSV_COMPLETO = "\r\n".join([
    "Datum,02.12.24",
    "Uhrzeit,10:41:16",
    "[Auftragsdaten]",
    "Pruefauftragsnummer     ,824902015333.mpg",
    "Kommentar1              ,",
    "Kunde                   ,VW",
    "",
    "[Messprogrammseite 1]",
    "Zyklen,Hub,Mittelpos",
    "0,75,1330",
    "1,50,1330",
])

LOG_PROD = "\n".join([
    "********************",
    "***18:5:2018       17:42:25",
    "***ARCHIVO= 481700012632.Prod  CARRERA= 80",
    "***VELOC=125  31  0  0  0",
    "********************",
    "18:5:2018       17:59:42",
    "125 E690 C-86 Y+ V+",
    "31 E579 C-40 Y+ V+",
])


def _lineas(texto: str) -> list[str]:
    return td.decodificar(texto.encode("utf-8"))


def test_detecta_coma_como_separador():
    assert td.detectar_separador(_lineas(CSV_DOS_TABLAS)) == ","


def test_detecta_punto_y_coma():
    assert td.detectar_separador(_lineas("a;b;c\n1;2;3\n4;5;6")) == ";"


def test_log_sin_separadores_no_es_formato_tablas():
    lineas = _lineas(LOG_PROD)
    assert td.detectar_separador(lineas) is None
    assert td.es_formato_tablas(lineas) is False


def test_detecta_un_bloque_por_seccion_con_su_tipo():
    lineas = _lineas(CSV_COMPLETO)
    defs = td.detectar_tablas(lineas, ",")
    assert defs == [
        td.TablaDef(1, 2, con_encabezado=False),
        td.TablaDef(4, 6, con_encabezado=False),
        td.TablaDef(9, 11, con_encabezado=True),
    ]


def test_tablas_detectadas_automaticamente():
    lineas = _lineas(CSV_DOS_TABLAS)
    r = td.leer_tablas(lineas, ",", td.detectar_tablas(lineas, ","))
    assert [t.titulo for t in r.tablas] == ["Messprogrammseite 1", "QSStat"]
    assert [len(t.filas) for t in r.tablas] == [2, 2]


def test_rangos_del_pedido_real_se_corrigen_sin_copiar_el_error():
    # El usuario dijo "de la fila 1 a la N, la primer fila es el nombre de
    # las columnas", pero la fila 1 es un titulo: se usa la siguiente.
    lineas = _lineas(CSV_DOS_TABLAS)
    r = td.leer_tablas(lineas, ",", [td.TablaDef(1, 5), td.TablaDef(7, 9)])
    medicion, qsstat = r.tablas
    assert medicion.titulo == "Messprogrammseite 1"
    assert medicion.fila_encabezado == 2
    assert len(medicion.filas) == 2
    assert qsstat.titulo == "QSStat"
    assert qsstat.fila_encabezado == 7
    assert any("fila 5" in a and "titulo" in a for a in r.advertencias)
    assert any("se uso la fila 2 como encabezado" in a for a in r.advertencias)


def test_columnas_sin_nombre_y_columna_final_vacia():
    lineas = _lineas(CSV_DOS_TABLAS)
    r = td.leer_tablas(lineas, ",", td.detectar_tablas(lineas, ","))
    medicion, qsstat = r.tablas
    assert medicion.columnas[7:] == ["DruckUG-A1", "Columna 9", "Columna 10", "Columna 11", "Columna 12"]
    assert qsstat.columnas == ["Datum", "Uhrzeit", "Achse", "Bewertung", "Nummer", "ZugV1", "DruckV1"]
    assert qsstat.filas[0] == ["28.08.26", "04:37:28", "A1", "IO", 1, 1994, 0]


def test_bloque_clave_valor_sale_como_campo_valor():
    lineas = _lineas(CSV_COMPLETO)
    r = td.leer_tablas(lineas, ",", td.detectar_tablas(lineas, ","))
    auftrag = r.tablas[1]
    assert auftrag.titulo == "Auftragsdaten"
    assert auftrag.columnas == ["Campo", "Valor"]
    assert auftrag.filas[1] == ["Kommentar1", None]
    assert r.tablas[0].titulo == "Tabla 1"


@pytest.mark.parametrize("crudo, esperado", [
    ("", None),
    ("   0", 0),
    ("-12", -12),
    ("0.262", 0.262),
    ("001789002323", "001789002323"),
    ("1234567890123456", "1234567890123456"),
    ("28.08.26", "28.08.26"),
    ("VE1", "VE1"),
])
def test_conversion_de_valores(crudo, esperado):
    assert td._convertir(crudo) == esperado


@pytest.mark.parametrize("defs, mensaje", [
    ([], "ninguna tabla"),
    ([td.TablaDef(1, 99)], "no es valido"),
    ([td.TablaDef(0, 3)], "no es valido"),
    ([td.TablaDef(1, 5), td.TablaDef(5, 9)], "se superponen"),
])
def test_definiciones_invalidas_se_rechazan(defs, mensaje):
    with pytest.raises(ValueError, match=mensaje):
        td.leer_tablas(_lineas(CSV_DOS_TABLAS), ",", defs)


def test_tabla_solo_con_encabezado_se_rechaza():
    with pytest.raises(ValueError, match="solo tiene la fila de encabezado"):
        td.leer_tablas(_lineas(CSV_DOS_TABLAS), ",", [td.TablaDef(1, 2)])


def test_separador_fuera_de_la_lista_se_rechaza():
    with pytest.raises(ValueError, match="Separador no soportado"):
        td.leer_tablas(_lineas(CSV_DOS_TABLAS), " ", [td.TablaDef(1, 4)])


def test_excel_una_hoja_por_tabla_con_nombres_validos_y_unicos():
    resultado = td.ResultadoTablas(separador=",", tablas=[
        td.TablaLeida("QS:Stat/1", 1, 2, True, 1, ["a"], [[1]]),
        td.TablaLeida("QS:Stat/1", 3, 4, True, 3, ["b"], [[2]]),
    ])
    wb = openpyxl.load_workbook(io.BytesIO(td.escribir_excel(resultado)))
    assert wb.sheetnames == ["QS Stat 1", "QS Stat 1 (2)"]
    assert wb["QS Stat 1"]["A2"].value == 1


def test_archivo_real_h1312_completo():
    lineas = td.decodificar((DOCS / "H1312" / "824902015333_021224_000.csv").read_bytes())
    sep = td.detectar_separador(lineas)
    r = td.leer_tablas(lineas, sep, td.detectar_tablas(lineas, sep))
    assert [(t.titulo, len(t.filas), len(t.columnas)) for t in r.tablas] == [
        ("Tabla 1", 2, 2),
        ("Auftragsdaten", 38, 2),
        ("Messprogrammseite 1", 9, 12),
        ("QSStat", 4, 30),
    ]


def test_todos_los_csv_de_h1312_se_reconocen_como_tablas():
    archivos = sorted((DOCS / "H1312").glob("*.csv"))
    assert archivos
    no_reconocidos = [a.name for a in archivos if not td.es_formato_tablas(td.decodificar(a.read_bytes()))]
    assert no_reconocidos == []


def test_logs_prod_no_se_reconocen_como_tablas():
    for archivo in sorted(DOCS.glob("Prod*.t*")) + sorted(DOCS.glob("Prod*.T*")):
        with open(archivo, "rb") as f:
            muestra = f.read(200_000)
        assert td.es_formato_tablas(td.decodificar(muestra)) is False, archivo.name
