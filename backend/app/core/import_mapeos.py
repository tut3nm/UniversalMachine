"""Recordar mapeos de columnas usados en la importación (Nivel 4.6 del plan
de mejoras). Guarda, por máquina, el ÚLTIMO mapeo confirmado por el
usuario — no el índice de columna (que puede correrse de un archivo a
otro), sino el TEXTO del encabezado, para poder reencontrarlo aunque el
Excel/CSV siguiente tenga las columnas en otro orden.

Formato: {"busqueda": {"campo", "columna"} | null, "mapeo": {campo: encabezado}}.
El formato anterior (un dict plano solo con los datos) sigue leyéndose."""

from __future__ import annotations

import json
import os

NOMBRE_ARCHIVO = "import_mapeo.json"


def _ruta(data_dir: str) -> str:
    return os.path.join(data_dir, NOMBRE_ARCHIVO)


def cargar(data_dir: str) -> dict:
    """{"busqueda": {"campo", "columna"} | None, "mapeo": {campo: encabezado}}.
    Vacío si nunca se guardó nada, o si el archivo está corrupto (no es
    crítico: como mucho se pierde la sugerencia y el usuario mapea a mano)."""
    vacio = {"busqueda": None, "mapeo": {}}
    ruta = _ruta(data_dir)
    if not os.path.exists(ruta):
        return vacio
    try:
        with open(ruta, encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, json.JSONDecodeError, UnicodeDecodeError):
        return vacio
    if not isinstance(data, dict):
        return vacio
    if isinstance(data.get("mapeo"), dict):
        busqueda = data.get("busqueda")
        if not (isinstance(busqueda, dict) and busqueda.get("campo") and busqueda.get("columna")):
            busqueda = None
        return {"busqueda": busqueda, "mapeo": data["mapeo"]}
    # Formato anterior: dict plano {campo: encabezado}, sin clave de búsqueda.
    return {"busqueda": None, "mapeo": data}


def guardar(data_dir: str, busqueda: dict[str, str], mapeo: dict[str, str]) -> None:
    with open(_ruta(data_dir), "w", encoding="utf-8") as f:
        json.dump({"busqueda": busqueda, "mapeo": mapeo}, f, ensure_ascii=False, indent=2)


def aplicar_a_headers(mapeo_guardado: dict[str, str],
                      headers: list[str]) -> dict[str, int]:
    """Traduce el mapeo guardado (nombre_interno -> texto de encabezado) a
    índices de columna DENTRO de `headers`. Solo incluye los campos cuyo
    encabezado guardado sigue apareciendo tal cual en `headers` — si el
    archivo nuevo no trae esa columna, simplemente no se sugiere (el
    usuario la mapea a mano, como si no hubiera mapeo guardado)."""
    indice_por_texto = {h: i for i, h in enumerate(headers)}
    return {campo: indice_por_texto[texto]
            for campo, texto in mapeo_guardado.items()
            if texto in indice_por_texto}
