"""
Programa DSL de la pantalla "Generar desde plantilla" -> llamada a
plantillas_masivas.generar con las indicaciones del usuario (que columna
llena cada campo, de donde sale el nombre del archivo, que filas generar).
Sin operaciones, el resultado es identico al de la pantalla. Ver
PLAN_ASISTENTE_IA.md, seccion 12.2.
"""
from __future__ import annotations

from app.ai.dsl.interprete import Programa
from app.ai.plantillas_masivas import (
    PlantillaParseada,
    ResultadoGeneracion,
    _normalizar,
    _quitar_comentario,
    generar,
)


def lineas_con_campo(plantilla: PlantillaParseada) -> list[tuple[int, str]]:
    """(numero de linea 1-based, texto sin la nota '//') de cada linea con {...}."""
    return [
        (c.linea_index + 1, _quitar_comentario(plantilla.lineas[c.linea_index]).strip())
        for c in plantilla.campos
    ]


def ejecutar(
    programa: Programa, plantilla: PlantillaParseada, encabezados: list[str], filas: list[dict]
) -> ResultadoGeneracion:
    asignaciones: dict[int, str] = {}
    columna_nombre: str | None = None
    filtros: list[tuple[str, str]] = []

    for op in programa.operaciones:
        columna = op.args.get("columna")
        if not isinstance(columna, str):
            raise ValueError(f"{op.op}: falta la columna.")
        if op.op == "asignar_columna":
            linea = op.args.get("linea")
            if not isinstance(linea, int) or isinstance(linea, bool):
                raise ValueError("asignar_columna: 'linea' tiene que ser un numero de linea.")
            anterior = asignaciones.get(linea - 1)
            if anterior is not None and anterior != columna:
                raise ValueError(
                    f"La linea {linea} quedo asignada a dos columnas distintas "
                    f"('{anterior}' y '{columna}'): indica una sola."
                )
            asignaciones[linea - 1] = columna
        elif op.op == "nombre_archivo_desde":
            if columna_nombre is not None and columna_nombre != columna:
                raise ValueError(
                    f"El nombre del archivo quedo pedido desde dos columnas ('{columna_nombre}' y "
                    f"'{columna}'): indica una sola."
                )
            columna_nombre = columna
        elif op.op == "filtrar_filas":
            if columna not in encabezados:
                raise ValueError(f"filtrar_filas: el listado no tiene la columna '{columna}'.")
            filtros.append((columna, str(op.args.get("valor", ""))))
        else:
            raise ValueError(f"Operacion que no es de plantilla: '{op.op}'.")

    filas_elegidas = [
        f for f in filas
        if all(_normalizar(f.get(c, "")) == _normalizar(v) for c, v in filtros)
    ]
    if not filas_elegidas:
        raise ValueError("Ninguna fila del listado cumple el filtro pedido.")
    return generar(plantilla, encabezados, filas_elegidas, asignaciones, columna_nombre)
