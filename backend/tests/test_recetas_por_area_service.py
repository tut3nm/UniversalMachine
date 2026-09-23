import io
import zipfile
from pathlib import Path

import pytest

from app.services import recetas_por_area_service as svc

REPO_ROOT = Path(__file__).resolve().parents[2]
LISTADO_PATH = REPO_ROOT / "docs" / "Recetas_Andon.txt"


def test_previsualizar_caso_real():
    reporte = svc.previsualizar(LISTADO_PATH.read_bytes(), "Recetas_Andon.txt")
    assert reporte["cantidad_archivos"] == 54
    assert reporte["areas_usadas"] == {"HD": 12, "GPS2": 2}
    assert reporte["filas_sin_area"] == []
    assert "001789002162.13.5.def.txt" in reporte["nombres_archivo"]
    # Recetas_Andon.txt no repite sellados ni tiene campos vacios/no numericos
    assert reporte["hallazgos_listado"] == []
    # pero SI usa HD, que tiene el defecto real documentado en PLAN_ASISTENTE_IA.md
    assert any(
        h["regla"] == "descripcion_inconsistente_entre_variantes" for h in reporte["hallazgos_catalogo"]
    )


def test_previsualizar_no_audita_areas_que_el_listado_no_usa():
    # listado 100% GPS1 (sin defectos conocidos): no debe arrastrar el
    # hallazgo de HD solo porque HD tambien existe en el repo.
    contenido = b"amortiguador;sellado;area\n111;222;GPS1\n"
    reporte = svc.previsualizar(contenido, "listado.csv")
    assert reporte["hallazgos_catalogo"] == []


def test_previsualizar_detecta_codigo_repetido_en_el_listado():
    contenido = (
        "amortiguador;sellado;area\n"
        "111;222;HD\n"
        "999;222;HD\n"
    ).encode()
    reporte = svc.previsualizar(contenido, "listado.csv")
    assert any(h["regla"] == "codigo_repetido" for h in reporte["hallazgos_listado"])


def test_auditar_repositorio_encuentra_los_dos_defectos_documentados():
    reporte = svc.auditar_repositorio()
    reglas = {h["regla"] for h in reporte["hallazgos"]}
    assert "descripcion_inconsistente_entre_variantes" in reglas
    archivos = {h["archivo"] for h in reporte["hallazgos"]}
    assert "001789002323.17.def.txt" in archivos
    # Obsoletos/ queda fuera del alcance de auditar_repositorio() (mismo
    # criterio que cargar_catalogo): el segundo defecto documentado en el
    # plan no aparece aca, solo se lo puede ver apuntando directo a esa
    # carpeta (test_validacion_recetas.py lo cubre).
    assert "004981008611.20.def.txt" not in archivos


def test_generar_zip_caso_real():
    zip_bytes, nombre_zip = svc.generar_zip(LISTADO_PATH.read_bytes(), "Recetas_Andon.txt")
    assert nombre_zip == "Recetas_Andon_recetas.zip"

    with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zf:
        nombres = zf.namelist()
        assert len(nombres) == 54
        assert "GPS2/001789002162.13.5.def.txt" in nombres
        assert "HD/001789002361.15.def.txt" in nombres
        contenido = zf.read("HD/001789002361.15.def.txt").decode("utf-8")
        assert "#Codigo;001789002361" in contenido
        assert "#Descripcion;471700021861" in contenido


def test_listado_sin_filas_lanza_error():
    with pytest.raises(svc.RecetasPorAreaError):
        svc.previsualizar(b"amortiguador;sellado;area\n", "listado.csv")


def test_listado_sin_columna_area_lanza_error():
    with pytest.raises(svc.RecetasPorAreaError):
        svc.previsualizar(b"amortiguador;sellado\n1;2\n", "listado.csv")
