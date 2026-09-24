"""Flujo reconocer/guardar del nucleo de memoria (PLAN_MEMORIA_FORMATOS.md,
fases 1 a 3), a nivel de asistente_service: guardar un formato a partir de un
programa confirmado, y reconocerlo despues en el mismo archivo y en otro del
mismo formato (numeros de fila distintos, mismos titulos de seccion)."""
from pathlib import Path

import pytest

from app.ai import llm
from app.ai.memoria import almacen
from app.services import asistente_service as svc

import paths

DOCS = Path(__file__).resolve().parents[2] / "docs" / "H1312"


def _archivo(nombre: str) -> dict[str, svc.Archivo]:
    return {"datos": svc.Archivo(nombre, (DOCS / nombre).read_bytes())}


def _sin_indicaciones(system, user, grammar=None, max_tokens=768):
    return llm.LlmResult(True, "[]")


def _programa_detectado(archivos: dict[str, svc.Archivo]) -> list[dict]:
    r = svc.interpretar("mediciones", "tabulalo", archivos, ejecutar_llm=_sin_indicaciones)
    return r["programa"]


@pytest.fixture(autouse=True)
def _memoria_temporal(tmp_path, monkeypatch):
    monkeypatch.setattr(paths, "app_base_dir", lambda: str(tmp_path))


def test_reconocer_sin_formatos_guardados_da_ninguna():
    r = svc.reconocer("mediciones", _archivo("824902015333_280826_005.csv"))
    assert r == {"pantalla": "mediciones", "coincidencia": "ninguna", "candidatos": []}


def test_guardar_y_reconocer_el_mismo_archivo():
    archivos = _archivo("824902015333_280826_005.csv")
    programa = _programa_detectado(archivos)
    guardado = svc.guardar_formato("mediciones", "H1312 pieza X", programa, "explicacion", archivos)
    assert guardado["nombre"] == "H1312 pieza X"

    r = svc.reconocer("mediciones", archivos)
    assert r["coincidencia"] == "unica"
    assert r["formato"]["id"] == guardado["id"]
    assert r["formato"]["usos"] == 1
    assert [t["titulo"] for t in r["tablas"]] == ["Tabla 1", "Auftragsdaten", "Messprogrammseite 1", "QSStat"]


def test_reconocer_otro_archivo_del_mismo_formato_ancla_bien():
    archivos_005 = _archivo("824902015333_280826_005.csv")
    svc.guardar_formato(
        "mediciones", "H1312 pieza X", _programa_detectado(archivos_005), "", archivos_005
    )

    archivos_021224 = _archivo("824902015333_021224_000.csv")
    r = svc.reconocer("mediciones", archivos_021224)
    assert r["coincidencia"] == "unica"
    assert [t["titulo"] for t in r["tablas"]] == ["Tabla 1", "Auftragsdaten", "Messprogrammseite 1", "QSStat"]


def test_reconocer_archivo_de_otro_formato_da_ninguna():
    archivos_005 = _archivo("824902015333_280826_005.csv")
    svc.guardar_formato(
        "mediciones", "H1312 pieza X", _programa_detectado(archivos_005), "", archivos_005
    )
    r = svc.reconocer("mediciones", _archivo("824902015333_280826_006.csv"))
    assert r["coincidencia"] == "ninguna"


def test_guardar_formato_con_formato_id_lo_actualiza():
    archivos = _archivo("824902015333_280826_005.csv")
    guardado = svc.guardar_formato(
        "mediciones", "borrador", _programa_detectado(archivos), "", archivos
    )
    actualizado = svc.guardar_formato(
        "mediciones", "nombre final", _programa_detectado(archivos), "", archivos,
        formato_id=guardado["id"],
    )
    assert actualizado["id"] == guardado["id"]
    assert actualizado["nombre"] == "nombre final"
    assert len(almacen.listar("mediciones")) == 1


def test_guardar_formato_sin_nombre_es_un_error():
    archivos = _archivo("824902015333_280826_005.csv")
    with pytest.raises(svc.AsistenteError, match="nombre"):
        svc.guardar_formato("mediciones", "   ", _programa_detectado(archivos), "", archivos)


# -- plantilla (fase 2) ---------------------------------------------------------

_RECETAS_DIR = Path(__file__).resolve().parents[2] / "docs" / "Recetas"
_PLANTILLA_PATH = _RECETAS_DIR / "plantilla.txt"
_LISTADO_PATH = Path(__file__).resolve().parents[2] / "docs" / "Recetas_Andon.txt"


def _archivos_plantilla(plantilla_bytes: bytes | None = None) -> dict[str, svc.Archivo]:
    return {
        "plantilla": svc.Archivo("plantilla.txt", plantilla_bytes or _PLANTILLA_PATH.read_bytes()),
        "listado": svc.Archivo(_LISTADO_PATH.name, _LISTADO_PATH.read_bytes()),
    }


def _stub_plantilla(system, user, grammar=None, max_tokens=768):
    # lo que el modelo emitiria si el usuario describe explicitamente la
    # asignacion (el "[]" sin indicaciones no genera programa: el llenado
    # automatico por comentario no pasa por el DSL, asi que no hay nada que
    # anclar - PLAN_MEMORIA_FORMATOS.md, 3.1: solo se guarda lo confirmado).
    return llm.LlmResult(
        True,
        '[{"op": "asignar_columna", "args": {"linea": 1, "columna": "sellado"}},'
        ' {"op": "asignar_columna", "args": {"linea": 3, "columna": "amortiguador"}},'
        ' {"op": "nombre_archivo_desde", "args": {"columna": "sellado"}}]',
    )


def _programa_plantilla_detectado(archivos: dict[str, svc.Archivo]) -> list[dict]:
    r = svc.interpretar(
        "plantilla", "el sellado en la 1, el amortiguador en la 3, nombre por sellado", archivos,
        ejecutar_llm=_stub_plantilla,
    )
    return r["programa"]


def test_reconocer_plantilla_sin_formatos_guardados_da_ninguna():
    r = svc.reconocer("plantilla", _archivos_plantilla())
    assert r == {"pantalla": "plantilla", "coincidencia": "ninguna", "candidatos": []}


def test_guardar_y_reconocer_la_misma_plantilla():
    archivos = _archivos_plantilla()
    programa = _programa_plantilla_detectado(archivos)
    guardado = svc.guardar_formato("plantilla", "Plantilla HD", programa, "", archivos)

    r = svc.reconocer("plantilla", archivos)
    assert r["coincidencia"] == "unica"
    assert r["formato"]["id"] == guardado["id"]
    assert [(c["linea"], c["columna"]) for c in r["campos"]] == [(1, "sellado"), (3, "amortiguador")]
    assert r["columna_nombre_archivo"] == "sellado"


def test_reconocer_otra_plantilla_del_mismo_formato_ancla_por_prefijo():
    archivos = _archivos_plantilla()
    svc.guardar_formato("plantilla", "Plantilla HD", _programa_plantilla_detectado(archivos), "", archivos)

    # misma plantilla, con una linea fija de mas arriba: los campos quedan en
    # otro numero de linea, pero los prefijos ('#Codigo;', '#Descripcion;')
    # son los mismos.
    original = _PLANTILLA_PATH.read_text(encoding="utf-8")
    corrida = ("#Nota;version 2\r\n" + original).encode("utf-8")
    archivos_corridos = _archivos_plantilla(corrida)

    r = svc.reconocer("plantilla", archivos_corridos)
    assert r["coincidencia"] == "unica"
    assert [(c["linea"], c["columna"]) for c in r["campos"]] == [(2, "sellado"), (4, "amortiguador")]
    assert r["columna_nombre_archivo"] == "sellado"


def test_reconocer_plantilla_distinta_da_ninguna():
    archivos = _archivos_plantilla()
    svc.guardar_formato("plantilla", "Plantilla HD", _programa_plantilla_detectado(archivos), "", archivos)

    otra = "#OtroCampo;{x}\r\n".encode("utf-8")
    r = svc.reconocer("plantilla", _archivos_plantilla(otra))
    assert r["coincidencia"] == "ninguna"


def test_guardar_formato_plantilla_sin_asignaciones_es_un_error():
    with pytest.raises(svc.AsistenteError, match="asignar"):
        svc.guardar_formato("plantilla", "x", [], "", _archivos_plantilla())


# -- recetas por area (fase 3) ---------------------------------------------------


def _archivos_recetas(listado_bytes: bytes | None = None) -> dict[str, svc.Archivo]:
    return {"listado": svc.Archivo(_LISTADO_PATH.name, listado_bytes or _LISTADO_PATH.read_bytes())}


def _stub_recetas(system, user, grammar=None, max_tokens=768):
    # nombrar_archivo es guardable; filtrar_filas y solo_sufijos no (seccion
    # 3.1): el ancla solo se queda con lo primero.
    return llm.LlmResult(
        True,
        '[{"op": "filtrar_filas", "args": {"columna": "area", "valor": "HD"}},'
        ' {"op": "expandir_por_catalogo", "args": {"solo_sufijos": ["15", "17"]}},'
        ' {"op": "nombrar_archivo", "args": {"patron": "{amortiguador}.{sufijo}.def.txt"}}]',
    )


def _programa_recetas_detectado(archivos: dict[str, svc.Archivo]) -> list[dict]:
    r = svc.interpretar(
        "recetas_por_area", "solo HD, .15 y .17, nombra con el amortiguador", archivos,
        ejecutar_llm=_stub_recetas,
    )
    return r["programa"]


def test_reconocer_recetas_sin_formatos_guardados_da_ninguna():
    r = svc.reconocer("recetas_por_area", _archivos_recetas())
    assert r == {"pantalla": "recetas_por_area", "coincidencia": "ninguna", "candidatos": []}


def test_guardar_recetas_solo_ancla_lo_guardable():
    archivos = _archivos_recetas()
    programa = _programa_recetas_detectado(archivos)
    guardado = svc.guardar_formato("recetas_por_area", "Andon HD .15/.17", programa, "", archivos)

    formato = almacen.obtener(guardado["id"])
    assert [o["op"] for o in formato.regla["operaciones"]] == ["nombrar_archivo"]


def test_guardar_y_reconocer_el_mismo_listado_de_recetas():
    archivos = _archivos_recetas()
    guardado = svc.guardar_formato(
        "recetas_por_area", "Andon", _programa_recetas_detectado(archivos), "", archivos
    )

    r = svc.reconocer("recetas_por_area", archivos)
    assert r["coincidencia"] == "unica"
    assert r["formato"]["id"] == guardado["id"]
    # expandir_por_catalogo vuelve SIN restriccion de sufijos (no se guarda
    # solo_sufijos); nombrar_archivo si se aplico.
    assert r["programa"] == [
        {"op": "expandir_por_catalogo", "args": {}},
        {"op": "nombrar_archivo", "args": {"patron": "{amortiguador}.{sufijo}.def.txt"}},
    ]


def test_reconocer_otro_listado_del_mismo_formato_por_encabezados_y_areas():
    archivos = _archivos_recetas()
    svc.guardar_formato("recetas_por_area", "Andon", _programa_recetas_detectado(archivos), "", archivos)

    # mismas columnas y mismas areas presentes (HD/GPS2), una fila mas: para
    # la huella (encabezados + areas normalizados) es el mismo formato.
    original = _LISTADO_PATH.read_bytes().decode("utf-8")
    otro = (original.rstrip("\n") + "\n481700099999\t001789099999\tHD\n").encode("utf-8")
    r = svc.reconocer("recetas_por_area", _archivos_recetas(otro))
    assert r["coincidencia"] == "unica"


def test_reconocer_listado_con_otras_areas_da_ninguna():
    archivos = _archivos_recetas()
    svc.guardar_formato("recetas_por_area", "Andon", _programa_recetas_detectado(archivos), "", archivos)

    # mismas columnas, pero ningun area en comun con el listado guardado
    # (HD/GPS2): la huella (encabezados + areas) no coincide ni se parece.
    otro = "amortiguador\tsellado\tarea\n471700021861\t001789002361\tGPS1\n".encode("utf-8")
    r = svc.reconocer("recetas_por_area", _archivos_recetas(otro))
    assert r["coincidencia"] == "ninguna"


def test_guardar_formato_recetas_sin_nada_guardable_es_un_error():
    archivos = _archivos_recetas()
    programa = svc.interpretar(
        "recetas_por_area", "generame las recetas", archivos, ejecutar_llm=_sin_indicaciones
    )["programa"]
    with pytest.raises(svc.AsistenteError, match="no ajusta nada guardable"):
        svc.guardar_formato("recetas_por_area", "x", programa, "", archivos)
