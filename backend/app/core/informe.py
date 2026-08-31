"""Informe de cambios exportable (Nivel 4.2 del plan de mejoras).

A diferencia de diferencias.py (que compara DOS snapshots, `actual` vs
`original`), esto exporta eventos del historial.jsonl de un período —
sirve para adjuntar al parte de cambio de receta: quién cambió qué,
cuándo, y con qué versión de la app."""

from __future__ import annotations

import json

ACCION_LABEL = {"alta": "Alta", "modificacion": "Modificación", "baja": "Baja",
                "importacion": "Importación", "restauracion": "Restauración",
                "limpieza": "Limpieza"}

ENCABEZADO = ["Fecha", "Usuario", "Acción", "Código", "Origen", "Versión",
             "Valores anteriores", "Valores nuevos"]


def a_filas_csv(eventos: list[dict]) -> list[list[str]]:
    """Convierte una lista de eventos (como los que devuelve
    historial.leer_eventos()) a filas listas para csv.writer. Los valores
    anteriores/nuevos se serializan como JSON compacto en una sola celda —
    son diccionarios de forma variable (dependen del perfil de cada
    máquina), no hay una columna fija razonable para cada campo."""
    filas = [list(ENCABEZADO)]
    for e in eventos:
        filas.append([
            e.get("timestamp", ""),
            e.get("usuario", ""),
            ACCION_LABEL.get(e.get("accion"), e.get("accion", "")),
            e.get("clave", ""),
            e.get("origen", ""),
            e.get("version") or "",
            json.dumps(e.get("anteriores"), ensure_ascii=False) if e.get("anteriores") else "",
            json.dumps(e.get("nuevos"), ensure_ascii=False) if e.get("nuevos") else "",
        ])
    return filas
