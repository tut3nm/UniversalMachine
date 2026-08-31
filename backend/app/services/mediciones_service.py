"""Envuelve ai/structure.py + ai/labeler.py + ai/generic_excel.py (de
Diagramadora, reutilizados tal cual) para procesar un archivo de mediciones
y devolver un .xlsx — equivalente web de universal.py. Bloqueante (corre en
el thread del request): la IA local tarda unos segundos por archivo, pero
Fase 1 es un solo operario por PC, igual que hoy (ver PLAN_WEBAPP.md)."""

from __future__ import annotations

import os
import tempfile
from typing import Any

from app import _bootstrap  # noqa: F401

import sys as _sys

_AI_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "ai")
if _AI_DIR not in _sys.path:
    _sys.path.insert(0, _AI_DIR)

import generic_excel
import labeler
import llm
import structure


def estado_ia() -> dict[str, Any]:
    ok, mensaje = llm.is_available()
    return {"disponible": ok, "mensaje": mensaje}


def procesar(nombre_datos: str, contenido_datos: bytes,
             nombre_anotaciones: str | None, contenido_anotaciones: bytes | None,
             use_ai: bool = True) -> dict[str, Any]:
    tmp_dir = tempfile.mkdtemp(prefix="mediciones_")
    data_path = os.path.join(tmp_dir, nombre_datos)
    with open(data_path, "wb") as f:
        f.write(contenido_datos)

    annot_path = None
    if nombre_anotaciones and contenido_anotaciones:
        annot_path = os.path.join(tmp_dir, nombre_anotaciones)
        with open(annot_path, "wb") as f:
            f.write(contenido_anotaciones)

    lines = structure.read_text_file(data_path)
    disc = structure.discover(lines)
    if not disc.records:
        raise ValueError(
            "No se encontraron mediciones que se repitan en este archivo. "
            "El programa busca un patrón de líneas que se repita.")

    annotated_text = None
    if annot_path:
        annotated_text = "".join(structure.read_text_file(annot_path))

    labels = labeler.build_labels(disc, annotated_text, use_ai=use_ai)

    base, _ = os.path.splitext(nombre_datos)
    out_path = os.path.join(tmp_dir, f"{base}.xlsx")
    generic_excel.write_excel(disc, labels, out_path, data_path, annotated_path=annot_path)

    return {
        "out_path": out_path,
        "out_filename": f"{base}.xlsx",
        "records": len(disc.records),
        "fields": len(disc.record_field_names),
        "configs": len(disc.config_snapshots),
        "period": disc.period,
        "unparsed": len(disc.unparsed_lines),
        "ai_messages": labels.messages,
    }
