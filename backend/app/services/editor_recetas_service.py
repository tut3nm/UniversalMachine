"""
Servicio del editor de recetas tipo matriz. Envuelve app/ai/csv_recipe.py
(motor puro, migrado de Diagramadora/ai/csv_recipe.py) con manejo de
archivos temporales, mismo criterio que mediciones_service.py.

El backend es *stateless* entre los dos pasos del flujo (PLAN_EDITOR_RECETAS_
MATRIZ.md, decision 4): "aplicar_cambios" recibe de nuevo el .csv original,
no depende de que "exportar_excel" haya guardado nada en el servidor.
Tampoco hay estado entre "previsualizar" y "aplicar_y_descargar": el front
manda los mismos dos archivos dos veces (previsualizar para mostrar el
reporte, aplicar_y_descargar para bajar el .csv), asi que ambos
recalculan todo desde cero. Es barato: son archivos chicos.
"""
from __future__ import annotations

import os
import re
import tempfile

from app import _bootstrap  # noqa: F401  (side effect: agrega app/core/ a sys.path)

import log_jsonl

from app.ai import csv_recipe

_ORIGEN_LOG = "editor_recetas"

_CARACTERES_INVALIDOS_WINDOWS = re.compile(r'[<>:"/\\|?*\x00-\x1f]')
_NOMBRES_RESERVADOS_WINDOWS = {
    "con", "prn", "aux", "nul",
    *(f"com{n}" for n in "123456789"), *(f"lpt{n}" for n in "123456789"),
}


class EditorRecetasError(ValueError):
    """Error de validacion de negocio (archivo invalido o mal formado)."""


def _nombre_base(nombre_archivo: str) -> str:
    return nombre_archivo.rsplit(".", 1)[0] if "." in nombre_archivo else nombre_archivo


def _nombre_seguro_para_disco(nombre: str) -> str:
    """El nombre de archivo que sube el usuario puede tener caracteres que
    Windows no admite en un path (`< > : " / \\ | ?` `*`, de control, o
    terminar en espacio/punto) o coincidir con un nombre reservado (`CON`,
    `NUL`, `COM1`...). Esto solo se usa para el path en el directorio
    temporal: el nombre que ve el usuario (devuelto al caller, y de ahi al
    header `Content-Disposition`) sigue siendo el original, sin tocar."""
    seguro = _CARACTERES_INVALIDOS_WINDOWS.sub("_", nombre).strip(" .")
    base = seguro.rsplit(".", 1)[0] if "." in seguro else seguro
    if not seguro or base.lower() in _NOMBRES_RESERVADOS_WINDOWS:
        seguro = f"_{seguro}" if seguro else "archivo"
    return seguro


def _guardar_temp(tmp_dir: str, nombre: str, contenido: bytes) -> str:
    path = os.path.join(tmp_dir, _nombre_seguro_para_disco(nombre))
    with open(path, "wb") as f:
        f.write(contenido)
    return path


def exportar_excel(csv_contenido: bytes, csv_nombre: str) -> tuple[bytes, str, dict]:
    """Paso 1: .csv original -> Excel editable. Devuelve (bytes, nombre, resumen)."""
    tmp_dir = tempfile.mkdtemp(prefix="editor_recetas_")
    csv_path = _guardar_temp(tmp_dir, csv_nombre, csv_contenido)

    try:
        receta = csv_recipe.read_recipe(csv_path)
    except ValueError as e:
        raise EditorRecetasError(str(e)) from e

    nombre_xlsx = f"{_nombre_base(csv_nombre)} (editable).xlsx"
    xlsx_path = os.path.join(tmp_dir, _nombre_seguro_para_disco(nombre_xlsx))
    csv_recipe.write_excel_recipe(receta, xlsx_path, csv_path)

    with open(xlsx_path, "rb") as f:
        xlsx_bytes = f.read()

    resumen = {"n_productos": len(receta.product_codes), "n_parametros": len(receta.params)}
    return xlsx_bytes, nombre_xlsx, resumen


def _reconstruir(
    csv_original_contenido: bytes, csv_original_nombre: str,
    xlsx_editado_contenido: bytes, xlsx_editado_nombre: str,
) -> tuple[csv_recipe.RecipeFile, csv_recipe.ReverseResult, str, str]:
    tmp_dir = tempfile.mkdtemp(prefix="editor_recetas_")
    csv_path = _guardar_temp(tmp_dir, csv_original_nombre, csv_original_contenido)
    xlsx_path = _guardar_temp(tmp_dir, xlsx_editado_nombre, xlsx_editado_contenido)

    try:
        receta = csv_recipe.read_recipe(csv_path)
        editado = csv_recipe.read_edited_excel(xlsx_path)
    except ValueError as e:
        raise EditorRecetasError(str(e)) from e

    nombre_salida = f"{_nombre_base(csv_original_nombre)} (actualizado).csv"
    salida_path = os.path.join(tmp_dir, _nombre_seguro_para_disco(nombre_salida))
    resultado = csv_recipe.rebuild_csv(csv_path, receta, editado, salida_path)
    if resultado.error:
        raise EditorRecetasError(resultado.error)
    return receta, resultado, salida_path, nombre_salida


def _serializar_cambios(cambios: list[csv_recipe.CellChange]) -> list[dict]:
    return [
        {"parametro": c.parametro, "producto": c.producto, "valor_anterior": c.valor_anterior, "valor_nuevo": c.valor_nuevo}
        for c in cambios
    ]


def previsualizar_cambios(
    csv_original_contenido: bytes, csv_original_nombre: str,
    xlsx_editado_contenido: bytes, xlsx_editado_nombre: str,
) -> dict:
    """Paso 2 (preview): reporte de cambios sin devolver el archivo. Si hay
    una ALERTA (la autoverificacion del motor encontro algo que no cierra),
    `bloqueado` queda en True: PLAN_EDITOR_RECETAS_MATRIZ.md decision 2 dice
    que en ese caso no se ofrece la descarga."""
    _receta, resultado, _salida_path, _nombre_salida = _reconstruir(
        csv_original_contenido, csv_original_nombre, xlsx_editado_contenido, xlsx_editado_nombre,
    )
    return {
        "cantidad_cambios": len(resultado.changes),
        "cambios": _serializar_cambios(resultado.changes),
        "advertencias": resultado.warnings,
        "bloqueado": not resultado.ok,
    }


def aplicar_y_descargar(
    csv_original_contenido: bytes, csv_original_nombre: str,
    xlsx_editado_contenido: bytes, xlsx_editado_nombre: str,
) -> tuple[bytes, str, dict]:
    """Paso 2 (descarga): recalcula todo de nuevo (ver docstring del modulo)
    y devuelve el .csv reconstruido. Rechaza si hay ALERTA, aunque el front
    ya deberia haber ocultado el boton: es la misma regla aplicada tambien
    del lado del servidor, no solo en la UI."""
    receta, resultado, salida_path, nombre_salida = _reconstruir(
        csv_original_contenido, csv_original_nombre, xlsx_editado_contenido, xlsx_editado_nombre,
    )
    if not resultado.ok:
        raise EditorRecetasError(
            "La autoverificacion del archivo reconstruido encontro un problema: "
            + " | ".join(w for w in resultado.warnings if w.startswith("ALERTA"))
        )

    with open(salida_path, "rb") as f:
        csv_bytes = f.read()

    log_jsonl.registrar(_ORIGEN_LOG, {
        "archivo": csv_original_nombre,
        "cantidad_cambios": len(resultado.changes),
        "productos": len(receta.product_codes),
    })

    resumen = {"cantidad_cambios": len(resultado.changes), "advertencias": resultado.warnings}
    return csv_bytes, nombre_salida, resumen
