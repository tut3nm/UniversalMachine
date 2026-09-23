"""
Interprete del DSL: ejecuta un Programa (lista de operaciones) contra un
CatalogoArea real y produce archivos, byte a byte igual que si se hubiese
usado generar_por_area() cuando el programa no pisa ningun default (ver el
test de equivalencia en test_dsl_interprete.py y PLAN_ASISTENTE_IA.md seccion
9).

Nunca escribe a disco ni genera contenido: solo recombina lineas que ya
existian en las plantillas de referencia, con valores que ya existian en el
listado subido. Todo lo que un programa puede pedir se valida ANTES de
generar nada (validar_programa) contra lo que el contexto realmente tiene -
esa validacion es la que hace imposible, no solo improbable, que una columna
o un sufijo inventado lleguen a un archivo (contrato de seguridad, seccion
3.4 del plan).
"""
from __future__ import annotations

from dataclasses import dataclass, field

from app.ai.dsl.operaciones import CAMPOS_RECETA, OPERACION_DESCONOCIDO, TODAS
from app.ai.plantillas_masivas import _normalizar
from app.ai.recetas_por_area import (
    CatalogoArea,
    _LINEA_CODIGO_PREFIJO,
    _LINEA_DESCRIPCION_PREFIJO,
    _buscar_columna_unica,
)

_PREFIJO_POR_CAMPO = {
    "#Codigo": _LINEA_CODIGO_PREFIJO,
    "#Descripcion": _LINEA_DESCRIPCION_PREFIJO,
}


@dataclass(frozen=True)
class Operacion:
    op: str
    args: dict = field(default_factory=dict)


@dataclass(frozen=True)
class Programa:
    operaciones: tuple[Operacion, ...] = ()

    @property
    def es_desconocido(self) -> bool:
        return any(o.op == OPERACION_DESCONOCIDO for o in self.operaciones)


@dataclass(frozen=True)
class ArchivoGenerado:
    nombre_archivo: str
    contenido: str
    area: str = ""
    carpeta: str = ""  # solo si el programa uso agrupar_salida_por; si no, el area es la carpeta natural
    fila_origen: int = 0


@dataclass
class ResultadoPrograma:
    archivos: list[ArchivoGenerado] = field(default_factory=list)
    advertencias: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class ContextoRecetas:
    """Lo que el interprete necesita para ejecutar el mundo 'recetas por
    area': el listado subido ya parseado y los catalogos de referencia."""

    encabezados: list[str]
    filas: list[dict]
    catalogos: dict[str, CatalogoArea]  # clave: area normalizada
    col_area: str
    col_sellado: str
    col_amortiguador: str


def construir_contexto(
    catalogos: dict[str, CatalogoArea], encabezados: list[str], filas: list[dict]
) -> ContextoRecetas:
    """Resuelve las columnas obligatorias del listado, igual que
    generar_por_area(): exactamente una columna 'sellado', 'amortiguador' y
    'area' (por nombre normalizado). Las operaciones finas pueden despues
    reemplazar CUAL columna alimenta cada campo, pero estas tres tienen que
    existir siempre porque #Codigo/#Descripcion/area son los defaults."""
    encabezados_norm = {h: _normalizar(h) for h in encabezados}
    return ContextoRecetas(
        encabezados=list(encabezados),
        filas=filas,
        catalogos=catalogos,
        col_area=_buscar_columna_unica(encabezados_norm, "area"),
        col_sellado=_buscar_columna_unica(encabezados_norm, "sellado"),
        col_amortiguador=_buscar_columna_unica(encabezados_norm, "amortiguador"),
    )


def _sufijos_disponibles(ctx: ContextoRecetas) -> set[str]:
    return {v.sufijo for catalogo in ctx.catalogos.values() for v in catalogo.variantes}


def validar_programa(programa: Programa, ctx: ContextoRecetas) -> None:
    """Levanta ValueError con un mensaje claro si el programa referencia algo
    que el contexto no tiene, o si esta mal formado. Se llama siempre antes
    de ejecutar_programa()."""
    if programa.es_desconocido:
        raise ValueError(
            "El programa quedo marcado 'desconocido': no hay nada para ejecutar "
            "todavia, hace falta que complete los datos a mano."
        )

    encabezados = set(ctx.encabezados)
    sufijos_validos = _sufijos_disponibles(ctx)
    cantidad_expandir = 0
    cantidad_nombrar = 0

    for operacion in programa.operaciones:
        definicion = TODAS.get(operacion.op)
        if definicion is None:
            raise ValueError(f"Operacion desconocida: '{operacion.op}'.")
        if definicion.capa != "fina":
            raise ValueError(
                f"'{operacion.op}' es una operacion gruesa: el interprete de "
                "recetas solo ejecuta operaciones finas (filtrar_filas, "
                "expandir_por_catalogo, etc.)."
            )

        if operacion.op == "filtrar_filas":
            col = operacion.args.get("columna")
            if col not in encabezados:
                raise ValueError(f"filtrar_filas: la columna '{col}' no existe en el listado.")
        elif operacion.op == "expandir_por_catalogo":
            cantidad_expandir += 1
            for sufijo in operacion.args.get("solo_sufijos") or []:
                if sufijo not in sufijos_validos:
                    raise ValueError(
                        f"expandir_por_catalogo: el sufijo '{sufijo}' no existe en "
                        "ningun catalogo de area cargado."
                    )
        elif operacion.op == "reemplazar_campo":
            campo = operacion.args.get("campo")
            col = operacion.args.get("columna")
            if campo not in CAMPOS_RECETA:
                raise ValueError(f"reemplazar_campo: campo invalido '{campo}' (debe ser #Codigo o #Descripcion).")
            if col not in encabezados:
                raise ValueError(f"reemplazar_campo: la columna '{col}' no existe en el listado.")
        elif operacion.op == "nombrar_archivo":
            cantidad_nombrar += 1
            if not operacion.args.get("patron"):
                raise ValueError("nombrar_archivo: falta el patron.")
        elif operacion.op == "agrupar_salida_por":
            col = operacion.args.get("columna")
            if col not in encabezados:
                raise ValueError(f"agrupar_salida_por: la columna '{col}' no existe en el listado.")

    if cantidad_expandir == 0:
        raise ValueError(
            "El programa no tiene 'expandir_por_catalogo': no generaria ningun archivo."
        )
    if cantidad_expandir > 1:
        raise ValueError("El programa no puede tener mas de un 'expandir_por_catalogo'.")
    if cantidad_nombrar > 1:
        raise ValueError("El programa no puede tener mas de un 'nombrar_archivo'.")


def _cumple_filtro(valor_fila: str, valor_esperado: str) -> bool:
    return valor_fila.strip() == valor_esperado.strip()


def ejecutar_programa(programa: Programa, ctx: ContextoRecetas) -> ResultadoPrograma:
    """Ejecuta el programa ya validado. Reproduce exactamente
    generar_por_area() cuando el unico operando es expandir_por_catalogo sin
    argumentos (el caso por defecto de la card 'Generar recetas por area')."""
    validar_programa(programa, ctx)

    filas_indexadas = list(enumerate(ctx.filas, start=1))
    mapeo_campo = {"#Codigo": ctx.col_sellado, "#Descripcion": ctx.col_amortiguador}
    patron_nombre = "{" + _clave_slot(ctx.col_sellado) + "}.{sufijo}.def.txt"
    solo_sufijos: set[str] | None = None
    columna_agrupado: str | None = None
    quitar_comentarios = False

    for operacion in programa.operaciones:
        if operacion.op == "filtrar_filas":
            col = operacion.args["columna"]
            valor = operacion.args["valor"]
            filas_indexadas = [
                (i, f) for i, f in filas_indexadas if _cumple_filtro(f.get(col, ""), valor)
            ]
        elif operacion.op == "expandir_por_catalogo":
            sufijos = operacion.args.get("solo_sufijos") or []
            solo_sufijos = set(sufijos) if sufijos else None
        elif operacion.op == "reemplazar_campo":
            mapeo_campo[operacion.args["campo"]] = operacion.args["columna"]
        elif operacion.op == "nombrar_archivo":
            patron_nombre = operacion.args["patron"]
        elif operacion.op == "agrupar_salida_por":
            columna_agrupado = operacion.args["columna"]
        elif operacion.op == "quitar_comentarios":
            quitar_comentarios = True

    resultado = ResultadoPrograma()
    nombres_usados: dict[str, int] = {}

    for i, fila in filas_indexadas:
        area_valor = fila.get(ctx.col_area, "").strip()
        catalogo = ctx.catalogos.get(_normalizar(area_valor))
        if catalogo is None:
            resultado.advertencias.append(f"Fila {i}: area '{area_valor}' sin catalogo, se omite.")
            continue

        for variante in catalogo.variantes:
            if solo_sufijos is not None and variante.sufijo not in solo_sufijos:
                continue

            lineas = list(variante.lineas)
            for campo, columna in mapeo_campo.items():
                valor = fila.get(columna, "").strip()
                idx = variante.linea_codigo if campo == "#Codigo" else variante.linea_descripcion
                lineas[idx] = f"{_PREFIJO_POR_CAMPO[campo]}{valor}"

            if quitar_comentarios:
                lineas = [l for l in lineas if not l.strip().startswith("//")]

            slots = {_clave_slot(h): fila.get(h, "").strip() for h in ctx.encabezados}
            slots["sufijo"] = variante.sufijo
            slots["area"] = catalogo.area
            try:
                base = patron_nombre.format(**slots)
            except KeyError as exc:
                raise ValueError(f"nombrar_archivo: el patron usa un slot inexistente: {exc}") from exc

            nombre_archivo = base
            contador = nombres_usados.get(nombre_archivo, 0) + 1
            nombres_usados[nombre_archivo] = contador
            if contador > 1:
                if nombre_archivo.lower().endswith(".def.txt"):
                    raiz = nombre_archivo[: -len(".def.txt")]
                    nombre_archivo = f"{raiz}_{contador}.def.txt"
                else:
                    nombre_archivo = f"{nombre_archivo}_{contador}"

            carpeta = fila.get(columna_agrupado, "").strip() if columna_agrupado else ""

            resultado.archivos.append(
                ArchivoGenerado(
                    nombre_archivo=nombre_archivo,
                    contenido=variante.eol.join(lineas),
                    area=catalogo.area,
                    carpeta=carpeta,
                    fila_origen=i,
                )
            )

    return resultado


def _clave_slot(nombre_columna: str) -> str:
    """Normaliza un encabezado a una clave de slot valida para str.format
    (sin espacios ni caracteres raros), preservando el caso para que
    "{sellado}" siga funcionando tal cual lo escribe el usuario."""
    return "".join(c if c.isalnum() or c == "_" else "_" for c in nombre_columna.strip())
