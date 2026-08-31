"""Búsqueda y filtros avanzados (Nivel 4.7 del plan de mejoras).

Antes, la barra de búsqueda solo miraba el campo clave. Este módulo separa
la lógica de coincidencia (búsqueda de texto libre por cualquier campo
visible + filtros de rango numérico) de la UI, y agrega persistencia de
"filtros frecuentes" guardados por máquina."""

from __future__ import annotations

import json
import os

NOMBRE_ARCHIVO = "filtros_guardados.json"


# -- coincidencia --------------------------------------------------------------
def coincide_busqueda(record: dict, campos, query: str) -> bool:
    """True si `query` (ya en minúsculas, sin espacios de más) aparece como
    subcadena del valor de CUALQUIERA de `campos` (lista de Campo,
    normalmente profile.campos_visibles()). Sin query, siempre coincide."""
    if not query:
        return True
    return any(query in str(record.get(c.nombre_interno, "")).lower() for c in campos)


def coincide_rangos(record: dict, rangos: dict) -> bool:
    """`rangos`: {nombre_interno: (minimo, maximo)}, cualquiera de los dos
    puede ser None (sin límite de ese lado). Un registro sin valor para un
    campo filtrado no coincide (no hay forma de saber si estaría dentro del
    rango)."""
    for nombre_interno, (minimo, maximo) in rangos.items():
        valor = record.get(nombre_interno)
        if valor is None:
            return False
        if minimo is not None and valor < minimo:
            return False
        if maximo is not None and valor > maximo:
            return False
    return True


def filtrar(records: list[dict], campos_busqueda, query: str, rangos: dict) -> list[dict]:
    query = (query or "").strip().lower()
    return [r for r in records
            if coincide_busqueda(r, campos_busqueda, query) and coincide_rangos(r, rangos)]


# -- filtros frecuentes (persistencia por máquina) ------------------------------
def _ruta(data_dir: str) -> str:
    return os.path.join(data_dir, NOMBRE_ARCHIVO)


def cargar_guardados(data_dir: str) -> list[dict]:
    """Lista de presets: [{"nombre": str, "busqueda": str,
    "rangos": {nombre_interno: [minimo, maximo]}}, ...]. Vacía si nunca se
    guardó nada o el archivo está corrupto (no crítico: se pierde la lista
    de atajos, no ningún dato del catálogo)."""
    ruta = _ruta(data_dir)
    if not os.path.exists(ruta):
        return []
    try:
        with open(ruta, encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, list) else []
    except (OSError, json.JSONDecodeError, UnicodeDecodeError):
        return []


def guardar_lista(data_dir: str, presets: list[dict]) -> None:
    with open(_ruta(data_dir), "w", encoding="utf-8") as f:
        json.dump(presets, f, ensure_ascii=False, indent=2)


def agregar_o_reemplazar(data_dir: str, nombre: str, busqueda: str,
                         rangos: dict) -> list[dict]:
    """Guarda (o reemplaza si ya existía un preset con ese nombre) y
    devuelve la lista actualizada."""
    presets = [p for p in cargar_guardados(data_dir) if p.get("nombre") != nombre]
    presets.append({"nombre": nombre, "busqueda": busqueda,
                    "rangos": {k: list(v) for k, v in rangos.items()}})
    guardar_lista(data_dir, presets)
    return presets


def eliminar(data_dir: str, nombre: str) -> list[dict]:
    presets = [p for p in cargar_guardados(data_dir) if p.get("nombre") != nombre]
    guardar_lista(data_dir, presets)
    return presets
