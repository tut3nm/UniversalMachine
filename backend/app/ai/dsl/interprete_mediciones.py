"""
Programa DSL de la pantalla Mediciones -> estructura para
tablas_delimitadas.leer_tablas. El programa final siempre tiene exactamente
un usar_separador y un definir_tablas: lo que el usuario no indico sale de la
deteccion automatica (completar()), asi lo que queda en el log es lo que
realmente se ejecuto. Ver PLAN_ASISTENTE_IA.md, seccion 12.1.
"""
from __future__ import annotations

from app.ai import tablas_delimitadas as td
from app.ai.dsl.interprete import Operacion, Programa


def _tipo(con_encabezado: bool) -> str:
    return "tabla" if con_encabezado else "listado"


def _op_tablas(defs: list[td.TablaDef]) -> Operacion:
    return Operacion("definir_tablas", {"tablas": [
        {"desde": d.desde, "hasta": d.hasta, "tipo": _tipo(d.con_encabezado)} for d in defs
    ]})


def completar(operaciones_modelo: list[Operacion], lineas: list[str]) -> Programa:
    separador = next((o.args.get("separador") for o in operaciones_modelo if o.op == "usar_separador"), None)
    tablas = next((o.args.get("tablas") for o in operaciones_modelo if o.op == "definir_tablas"), None)
    if separador is None:
        separador = td.detectar_separador(lineas)
        if separador is None:
            raise ValueError(
                "No se reconoce un separador de columnas (coma, punto y coma, tab o |) en el archivo."
            )
    op_tablas = (
        Operacion("definir_tablas", {"tablas": tablas}) if tablas is not None
        else _op_tablas(td.detectar_tablas(lineas, separador))
    )
    return Programa(operaciones=(Operacion("usar_separador", {"separador": separador}), op_tablas))


def _tabla_def(item, lineas: list[str], sep: str) -> td.TablaDef:
    if not isinstance(item, dict):
        raise ValueError("Cada tabla tiene que tener 'desde' y 'hasta'.")
    desde, hasta = item.get("desde"), item.get("hasta")
    for nombre, valor in (("desde", desde), ("hasta", hasta)):
        if not isinstance(valor, int) or isinstance(valor, bool):
            raise ValueError(f"'{nombre}' tiene que ser un numero de fila.")
    tipo = item.get("tipo")
    if tipo not in ("listado", "tabla"):
        # respaldo determinista (PLAN_MEMORIA_FORMATOS.md, 5.1): un rango con
        # forma clave,valor que el usuario/modelo no describio queda como
        # listado; el resto, como tabla.
        tipo = "listado" if td.es_bloque_clave_valor(lineas, sep, desde, hasta) else "tabla"
    return td.TablaDef(desde=desde, hasta=hasta, con_encabezado=(tipo == "tabla"))


def ejecutar(programa: Programa, lineas: list[str]) -> td.ResultadoTablas:
    separadores = [o for o in programa.operaciones if o.op == "usar_separador"]
    definiciones = [o for o in programa.operaciones if o.op == "definir_tablas"]
    otras = [o.op for o in programa.operaciones if o.op not in ("usar_separador", "definir_tablas")]
    if otras:
        raise ValueError(f"Operacion que no es de mediciones: '{otras[0]}'.")
    if len(separadores) != 1 or len(definiciones) != 1:
        raise ValueError("El programa tiene que tener exactamente un usar_separador y un definir_tablas.")

    tablas = definiciones[0].args.get("tablas")
    if not isinstance(tablas, list):
        raise ValueError("definir_tablas necesita una lista de tablas.")
    sep = separadores[0].args.get("separador")
    return td.leer_tablas(lineas, sep, [_tabla_def(t, lineas, sep) for t in tablas])
