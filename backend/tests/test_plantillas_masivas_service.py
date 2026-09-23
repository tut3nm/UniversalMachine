import io
import zipfile
from pathlib import Path

import pytest

from app.services import plantillas_masivas_service as svc

REPO_ROOT = Path(__file__).resolve().parents[2]
PLANTILLA_PATH = REPO_ROOT / "docs" / "Recetas" / "plantilla.txt"
LISTADO_PATH = REPO_ROOT / "docs" / "Recetas_Andon.txt"


def _plantilla_bytes() -> bytes:
    return PLANTILLA_PATH.read_bytes()


def _listado_bytes() -> bytes:
    return LISTADO_PATH.read_bytes()


def test_previsualizar_caso_base():
    reporte = svc.previsualizar(
        _plantilla_bytes(), "plantilla.txt", _listado_bytes(), "Recetas_Andon.txt"
    )
    assert reporte["cantidad_archivos"] == 14
    assert reporte["columnas_sin_uso"] == ["area"]
    assert reporte["lineas_ignoradas"] == []
    assert "001789002162.txt" in reporte["nombres_archivo"]


def test_generar_zip_caso_base():
    zip_bytes, nombre_zip = svc.generar_zip(
        _plantilla_bytes(), "plantilla.txt", _listado_bytes(), "Recetas_Andon.txt"
    )
    assert nombre_zip == "plantilla.zip"

    with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zf:
        nombres = zf.namelist()
        assert len(nombres) == 14
        assert "001789002162.txt" in nombres
        contenido = zf.read("001789002162.txt").decode("utf-8")
        assert "#Codigo;001789002162" in contenido
        assert "#Descripcion;301700019344" in contenido


def test_plantilla_sin_campos_variables_lanza_error():
    with pytest.raises(svc.PlantillasMasivasError):
        svc.previsualizar(
            b"#Codigo;0049810086\n", "plantilla.txt", _listado_bytes(), "Recetas_Andon.txt"
        )


def test_plantilla_xlsx_no_soportada_lanza_error():
    with pytest.raises(svc.PlantillasMasivasError):
        svc.previsualizar(b"", "plantilla.xlsx", _listado_bytes(), "Recetas_Andon.txt")


def test_listado_sin_filas_lanza_error():
    with pytest.raises(svc.PlantillasMasivasError):
        svc.previsualizar(
            _plantilla_bytes(), "plantilla.txt",
            b"amortiguador;sellado;area\n", "listado.csv",
        )
