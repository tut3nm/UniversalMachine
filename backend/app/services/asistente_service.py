"""
Servicio del asistente embebido. Cada pantalla le pasa sus archivos y el
pedido del usuario; el asistente traduce el pedido en operaciones sobre ESOS
archivos (nunca deriva a otra pantalla ni explica el sistema) y arma la vista
previa. Ver PLAN_ASISTENTE_IA.md, seccion 12.

- interpretar(): pedido + archivos -> programa propuesto + vista previa (usa IA).
- previsualizar(): programa editado en la tarjeta + archivos -> vista previa (sin IA).
- ejecutar(): programa + archivos -> archivo final (.zip o .xlsx) + log.
"""
from __future__ import annotations

import getpass
import io
import zipfile
from dataclasses import dataclass
from pathlib import Path

from app.ai import tablas_delimitadas as td
from app.ai import validacion_recetas
from app.ai.dsl import interprete_mediciones, interprete_plantilla
from app.ai.dsl import log as dsl_log
from app.ai.memoria import almacen, anclaje, huellas
from app.ai.dsl.interprete import (
    CatalogoArea,
    ContextoRecetas,
    Operacion,
    Programa,
    construir_contexto,
    ejecutar_programa,
    validar_programa,
)
from app.ai.dsl.operaciones import (
    PANTALLA_MEDICIONES,
    PANTALLA_PLANTILLA,
    PANTALLA_RECETAS,
    PANTALLAS,
)
from app.ai.dsl.planificador import (
    Plan,
    planificar_mediciones,
    planificar_plantilla,
    planificar_recetas,
    rangos_mencionados,
)
from app.ai.plantillas_masivas import _normalizar, leer_listado
from app.ai.recetas_por_area import cargar_catalogo
from app.services import plantillas_masivas_service

_AREAS = {"HD": "RecetasHD", "GPS1": "RecetasGPS1", "GPS2": "RecetasGPS2"}

ARCHIVOS_POR_PANTALLA: dict[str, tuple[str, ...]] = {
    PANTALLA_RECETAS: ("listado",),
    PANTALLA_MEDICIONES: ("datos",),
    PANTALLA_PLANTILLA: ("plantilla", "listado"),
}

_NOMBRE_ARCHIVO = {"listado": "el listado", "datos": "el archivo de datos", "plantilla": "la plantilla"}

MEDIA_ZIP = "application/zip"
MEDIA_XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


class AsistenteError(ValueError):
    """Error de validacion de negocio (pantalla, archivos o programa invalidos)."""


@dataclass(frozen=True)
class Archivo:
    nombre: str
    contenido: bytes


@dataclass(frozen=True)
class Salida:
    contenido: bytes
    nombre: str
    media_type: str
    resumen: dict


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[3]


def _validar_pantalla(pantalla: str) -> None:
    if pantalla not in PANTALLAS:
        raise AsistenteError(f"Pantalla desconocida: '{pantalla}'.")


def _faltantes(pantalla: str, archivos: dict[str, Archivo]) -> list[str]:
    return [_NOMBRE_ARCHIVO[a] for a in ARCHIVOS_POR_PANTALLA[pantalla] if a not in archivos]


def _serializar(operaciones) -> list[dict]:
    return [{"op": o.op, "args": o.args} for o in operaciones]


def _programa_desde_json(data) -> Programa:
    if not isinstance(data, list):
        raise AsistenteError("El programa debe ser una lista de operaciones.")
    operaciones = []
    for item in data:
        if not isinstance(item, dict) or not isinstance(item.get("op"), str):
            raise AsistenteError("Cada operacion debe tener 'op' (string) y 'args' (objeto).")
        args = item.get("args") or {}
        if not isinstance(args, dict):
            raise AsistenteError("Los 'args' de cada operacion deben ser un objeto.")
        operaciones.append(Operacion(item["op"], args))
    return Programa(operaciones=tuple(operaciones))


# ---------------------------------------------------------------------------
# Recetas por area
# ---------------------------------------------------------------------------


def _cargar_catalogos() -> dict[str, CatalogoArea]:
    base = _repo_root() / "docs" / "Recetas"
    try:
        return {
            _normalizar(area): cargar_catalogo(base / carpeta, area)
            for area, carpeta in _AREAS.items()
        }
    except (OSError, ValueError) as e:
        raise AsistenteError(f"No se pudieron cargar las plantillas de referencia: {e}") from e


def _contexto_recetas(listado: Archivo) -> ContextoRecetas:
    try:
        encabezados, filas = leer_listado(listado.contenido, listado.nombre)
    except ValueError as e:
        raise AsistenteError(str(e)) from e
    if not filas:
        raise AsistenteError("El listado no tiene filas de datos.")
    try:
        return construir_contexto(_cargar_catalogos(), encabezados, filas)
    except ValueError as e:
        raise AsistenteError(str(e)) from e


def _vista_previa_recetas(programa: Programa, ctx: ContextoRecetas) -> dict:
    try:
        validar_programa(programa, ctx)
        vista_previa = ejecutar_programa(programa, ctx)
    except ValueError as e:
        return {"error_validacion": str(e)}

    hallazgos = validacion_recetas.validar_listado(
        ctx.filas, ctx.col_sellado, ctx.col_amortiguador, ctx.col_area
    )
    for area in {a.area for a in vista_previa.archivos}:
        carpeta = _AREAS.get(area)
        if carpeta is not None:
            hallazgos.extend(validacion_recetas.auditar_carpeta(_repo_root() / "docs" / "Recetas" / carpeta))
    return {
        "cantidad_archivos": len(vista_previa.archivos),
        "advertencias": vista_previa.advertencias,
        "hallazgos": [{"regla": h.regla, "archivo": h.archivo, "mensaje": h.mensaje} for h in hallazgos],
    }


def _ejecutar_recetas(programa: Programa, archivos: dict[str, Archivo]) -> Salida:
    listado = archivos["listado"]
    ctx = _contexto_recetas(listado)
    try:
        validar_programa(programa, ctx)
        resultado = ejecutar_programa(programa, ctx)
    except ValueError as e:
        raise AsistenteError(str(e)) from e

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for archivo in resultado.archivos:
            carpeta = archivo.carpeta or archivo.area
            ruta = f"{carpeta}/{archivo.nombre_archivo}" if carpeta else archivo.nombre_archivo
            zf.writestr(ruta, archivo.contenido)
    base = listado.nombre.rsplit(".", 1)[0] if "." in listado.nombre else listado.nombre
    return Salida(
        contenido=buf.getvalue(), nombre=f"{base}_asistente.zip", media_type=MEDIA_ZIP,
        resumen={"cantidad_archivos": len(resultado.archivos), "advertencias": resultado.advertencias},
    )


# ---------------------------------------------------------------------------
# Mediciones
# ---------------------------------------------------------------------------


def _lineas_datos(datos: Archivo) -> list[str]:
    lineas = td.decodificar(datos.contenido)
    if not lineas:
        raise AsistenteError("El archivo de datos esta vacio.")
    return lineas


def _describir_deteccion(lineas: list[str]) -> str:
    sep = td.detectar_separador(lineas)
    if sep is None:
        return "no se reconocio ningun separador"
    tablas = ", ".join(
        f"filas {d.desde}-{d.hasta}{'' if d.con_encabezado else ' (sin encabezado)'}"
        for d in td.detectar_tablas(lineas, sep)
    )
    return f"separador {sep!r}; tablas en {tablas}"


def _rangos_no_usados(texto: str, lineas: list[str], programa: Programa) -> list[str]:
    """Chequeo plan vs. pedido (PLAN_MEMORIA_FORMATOS.md, 5.1): rangos que el
    usuario menciono en el mensaje y que no quedaron en ninguna tabla del
    programa final se avisan en la pantalla."""
    definicion = next((o for o in programa.operaciones if o.op == "definir_tablas"), None)
    usados = {
        (t.get("desde"), t.get("hasta"))
        for t in (definicion.args.get("tablas") or []) if isinstance(t, dict)
    } if definicion else set()
    return [
        f"Mencionaste la fila {desde}" + (f"-{hasta}" if hasta != desde else "")
        + ", pero no quedo en ninguna tabla."
        for desde, hasta in rangos_mencionados(texto, len(lineas))
        if (desde, hasta) not in usados
    ]


def _vista_previa_mediciones(programa: Programa, lineas: list[str]) -> dict:
    try:
        resultado = interprete_mediciones.ejecutar(programa, lineas)
    except ValueError as e:
        return {"error_validacion": str(e), "total_lineas": len(lineas)}
    return {
        "total_lineas": len(lineas),
        "separador": resultado.separador,
        "tablas": [td.resumen_tabla(t) for t in resultado.tablas],
        "advertencias": resultado.advertencias,
    }


def _ejecutar_mediciones(programa: Programa, archivos: dict[str, Archivo]) -> Salida:
    datos = archivos["datos"]
    try:
        resultado = interprete_mediciones.ejecutar(programa, _lineas_datos(datos))
    except ValueError as e:
        raise AsistenteError(str(e)) from e
    base = datos.nombre.rsplit(".", 1)[0] if "." in datos.nombre else datos.nombre
    return Salida(
        contenido=td.escribir_excel(resultado), nombre=f"{base}.xlsx", media_type=MEDIA_XLSX,
        resumen={"cantidad_archivos": 1, "cantidad_tablas": len(resultado.tablas),
                 "advertencias": resultado.advertencias},
    )


# ---------------------------------------------------------------------------
# Plantilla
# ---------------------------------------------------------------------------


def _cargar_plantilla(archivos: dict[str, Archivo]):
    plantilla, listado = archivos["plantilla"], archivos["listado"]
    try:
        return plantillas_masivas_service.cargar(
            plantilla.contenido, plantilla.nombre, listado.contenido, listado.nombre
        )
    except ValueError as e:
        raise AsistenteError(str(e)) from e


def _vista_previa_plantilla(programa: Programa, plantilla, encabezados, filas) -> dict:
    lineas = dict(interprete_plantilla.lineas_con_campo(plantilla))
    try:
        resultado = interprete_plantilla.ejecutar(programa, plantilla, encabezados, filas)
    except ValueError as e:
        return {"error_validacion": str(e)}
    return {
        "cantidad_archivos": len(resultado.archivos),
        "nombres_archivo": [a.nombre_archivo for a in resultado.archivos[:10]],
        "campos": [
            {"linea": c.linea_index + 1, "texto": lineas[c.linea_index + 1], "columna": c.columna_listado}
            for c in resultado.campos
        ],
        "columna_nombre_archivo": resultado.columna_nombre_archivo,
        "columnas_sin_uso": resultado.columnas_sin_uso,
    }


def _ejecutar_plantilla(programa: Programa, archivos: dict[str, Archivo]) -> Salida:
    plantilla, encabezados, filas = _cargar_plantilla(archivos)
    try:
        resultado = interprete_plantilla.ejecutar(programa, plantilla, encabezados, filas)
    except ValueError as e:
        raise AsistenteError(str(e)) from e
    contenido, nombre = plantillas_masivas_service.armar_zip(resultado, archivos["plantilla"].nombre)
    return Salida(
        contenido=contenido, nombre=nombre, media_type=MEDIA_ZIP,
        resumen={"cantidad_archivos": len(resultado.archivos), "advertencias": []},
    )


# ---------------------------------------------------------------------------
# Memoria de formatos (PLAN_MEMORIA_FORMATOS.md). Fases 1 a 3: mediciones,
# plantilla y recetas por area.
# ---------------------------------------------------------------------------


def _usuario_actual() -> str:
    try:
        return getpass.getuser()
    except OSError:
        return "desconocido"


def formato_resumen(f: almacen.Formato) -> dict:
    return {
        "id": f.id, "pantalla": f.pantalla, "nombre": f.nombre,
        "usos": f.usos, "creado_por": f.creado_por, "creado": f.creado, "ultimo_uso": f.ultimo_uso,
    }


def formato_detalle(f: almacen.Formato) -> dict:
    return {**formato_resumen(f), "explicacion": f.explicacion, "regla": f.regla}


def _candidato(f: almacen.Formato, similitud: float) -> dict:
    return {**formato_resumen(f), "similitud": round(similitud, 3)}


def _elegir_candidatos(formatos: list[almacen.Formato], huella: dict, similitud_fn) -> list[dict]:
    """Primero coincidencia exacta; si no hay, similitud >= umbral (varias
    candidatas cercanas quedan todas). Ver PLAN_MEMORIA_FORMATOS.md, seccion 6."""
    exactos = [f for f in formatos if f.huella == huella]
    if exactos:
        return [_candidato(exactos[0], 1.0)]
    puntuados = [(f, similitud_fn(huella, f.huella)) for f in formatos]
    return sorted(
        (_candidato(f, s) for f, s in puntuados if s >= huellas.UMBRAL_SIMILITUD),
        key=lambda c: -c["similitud"],
    )


def _reconocer_mediciones(archivos: dict[str, Archivo]) -> dict:
    lineas = _lineas_datos(archivos["datos"])
    huella = huellas.huella_mediciones(lineas)
    if huella is None:
        return {"coincidencia": "ninguna", "candidatos": []}
    candidatos = _elegir_candidatos(almacen.listar(PANTALLA_MEDICIONES), huella, huellas.similitud_mediciones)
    if len(candidatos) != 1:
        return {"coincidencia": "varias" if candidatos else "ninguna", "candidatos": candidatos}

    formato = almacen.obtener(candidatos[0]["id"])
    regla = anclaje.regla_desde_json(formato.regla)
    try:
        tablas = anclaje.aplicar_mediciones(regla, lineas)
    except ValueError as e:
        # ancla rota: se vuelve al paso "Ninguna" del flujo (seccion 4, paso 5).
        return {"coincidencia": "ninguna", "candidatos": [], "error_formato": str(e)}
    programa = Programa(operaciones=(
        Operacion("usar_separador", {"separador": regla.separador}),
        Operacion("definir_tablas", {"tablas": tablas}),
    ))
    almacen.registrar_uso(formato.id)
    return {
        "coincidencia": "unica",
        "formato": formato_resumen(almacen.obtener(formato.id)),
        "programa": _serializar(programa.operaciones),
        **_vista_previa_mediciones(programa, lineas),
    }


def _huella_y_regla_mediciones(programa: Programa, archivos: dict[str, Archivo]) -> tuple[dict, dict]:
    lineas = _lineas_datos(archivos["datos"])
    separador_op = next((o for o in programa.operaciones if o.op == "usar_separador"), None)
    definicion = next((o for o in programa.operaciones if o.op == "definir_tablas"), None)
    if separador_op is None or definicion is None:
        raise AsistenteError("El programa tiene que definir separador y tablas.")
    huella = huellas.huella_mediciones(lineas)
    if huella is None:
        raise AsistenteError("No se pudo calcular la huella de este archivo.")
    regla = anclaje.anclar_mediciones(
        definicion.args.get("tablas") or [], separador_op.args.get("separador"), lineas
    )
    return huella, anclaje.regla_a_json(regla)


def _reconocer_plantilla(archivos: dict[str, Archivo]) -> dict:
    plantilla, encabezados, filas = _cargar_plantilla(archivos)
    huella = huellas.huella_plantilla(plantilla, encabezados)
    if huella is None:
        return {"coincidencia": "ninguna", "candidatos": []}
    candidatos = _elegir_candidatos(almacen.listar(PANTALLA_PLANTILLA), huella, huellas.similitud_plantilla)
    if len(candidatos) != 1:
        return {"coincidencia": "varias" if candidatos else "ninguna", "candidatos": candidatos}

    formato = almacen.obtener(candidatos[0]["id"])
    regla = anclaje.regla_plantilla_desde_json(formato.regla)
    try:
        asignaciones, columna_nombre = anclaje.aplicar_plantilla(regla, plantilla, encabezados)
    except ValueError as e:
        return {"coincidencia": "ninguna", "candidatos": [], "error_formato": str(e)}
    operaciones = [Operacion("asignar_columna", a) for a in asignaciones]
    if columna_nombre is not None:
        operaciones.append(Operacion("nombre_archivo_desde", {"columna": columna_nombre}))
    programa = Programa(operaciones=tuple(operaciones))
    almacen.registrar_uso(formato.id)
    return {
        "coincidencia": "unica",
        "formato": formato_resumen(almacen.obtener(formato.id)),
        "programa": _serializar(programa.operaciones),
        **_vista_previa_plantilla(programa, plantilla, encabezados, filas),
    }


def _huella_y_regla_plantilla(programa: Programa, archivos: dict[str, Archivo]) -> tuple[dict, dict]:
    plantilla, encabezados, _filas = _cargar_plantilla(archivos)
    asignaciones = [
        {"linea": o.args.get("linea"), "columna": o.args.get("columna")}
        for o in programa.operaciones if o.op == "asignar_columna"
    ]
    columna_nombre = next(
        (o.args.get("columna") for o in programa.operaciones if o.op == "nombre_archivo_desde"), None
    )
    if not asignaciones and columna_nombre is None:
        raise AsistenteError(
            "El programa tiene que asignar al menos una columna o el nombre del archivo."
        )
    huella = huellas.huella_plantilla(plantilla, encabezados)
    if huella is None:
        raise AsistenteError("Esta plantilla no tiene ningun campo {...}.")
    regla = anclaje.anclar_plantilla(asignaciones, columna_nombre, plantilla)
    return huella, anclaje.regla_plantilla_a_json(regla)


def _reconocer_recetas(archivos: dict[str, Archivo]) -> dict:
    ctx = _contexto_recetas(archivos["listado"])
    huella = huellas.huella_recetas(ctx)
    if huella is None:
        return {"coincidencia": "ninguna", "candidatos": []}
    candidatos = _elegir_candidatos(almacen.listar(PANTALLA_RECETAS), huella, huellas.similitud_recetas)
    if len(candidatos) != 1:
        return {"coincidencia": "varias" if candidatos else "ninguna", "candidatos": candidatos}

    formato = almacen.obtener(candidatos[0]["id"])
    regla = anclaje.regla_recetas_desde_json(formato.regla)
    try:
        programa = anclaje.aplicar_recetas(regla, ctx)
    except ValueError as e:
        return {"coincidencia": "ninguna", "candidatos": [], "error_formato": str(e)}
    almacen.registrar_uso(formato.id)
    return {
        "coincidencia": "unica",
        "formato": formato_resumen(almacen.obtener(formato.id)),
        "programa": _serializar(programa.operaciones),
        **_vista_previa_recetas(programa, ctx),
    }


def _huella_y_regla_recetas(programa: Programa, archivos: dict[str, Archivo]) -> tuple[dict, dict]:
    ctx = _contexto_recetas(archivos["listado"])
    regla = anclaje.anclar_recetas(list(programa.operaciones))
    if not regla.operaciones:
        raise AsistenteError(
            "El programa no ajusta nada guardable (reemplazar_campo, nombrar_archivo, "
            "agrupar_salida_por o quitar_comentarios)."
        )
    huella = huellas.huella_recetas(ctx)
    if huella is None:
        raise AsistenteError("No se pudo calcular la huella de este listado.")
    return huella, anclaje.regla_recetas_a_json(regla)


_RECONOCER_POR_PANTALLA = {
    PANTALLA_MEDICIONES: _reconocer_mediciones,
    PANTALLA_PLANTILLA: _reconocer_plantilla,
    PANTALLA_RECETAS: _reconocer_recetas,
}
_HUELLA_Y_REGLA_POR_PANTALLA = {
    PANTALLA_MEDICIONES: _huella_y_regla_mediciones,
    PANTALLA_PLANTILLA: _huella_y_regla_plantilla,
    PANTALLA_RECETAS: _huella_y_regla_recetas,
}


def reconocer(pantalla: str, archivos: dict[str, Archivo]) -> dict:
    """Archivos de la pantalla -> formato reconocido (con programa y vista
    previa ya aplicados) o ninguno. Ver PLAN_MEMORIA_FORMATOS.md, seccion 4."""
    _validar_pantalla(pantalla)
    f = _RECONOCER_POR_PANTALLA.get(pantalla)
    if f is None or _faltantes(pantalla, archivos):
        return {"pantalla": pantalla, "coincidencia": "ninguna", "candidatos": []}
    return {"pantalla": pantalla, **f(archivos)}


def guardar_formato(
    pantalla: str,
    nombre: str,
    programa_data,
    explicacion: str,
    archivos: dict[str, Archivo],
    formato_id: str | None = None,
) -> dict:
    """Crea o actualiza (si `formato_id` viene de un formato reconocido y
    corregido) un formato a partir de un programa ya confirmado por el
    usuario. Ver PLAN_MEMORIA_FORMATOS.md, seccion 4, paso 4."""
    _validar_pantalla(pantalla)
    f = _HUELLA_Y_REGLA_POR_PANTALLA.get(pantalla)
    if f is None:
        raise AsistenteError("Guardar formatos todavia no esta disponible en esta pantalla.")
    if not nombre.strip():
        raise AsistenteError("El nombre del formato no puede estar vacio.")
    faltan = _faltantes(pantalla, archivos)
    if faltan:
        raise AsistenteError(f"Falta {', '.join(faltan)}.")

    programa = _programa_desde_json(programa_data)
    huella, regla_json = f(programa, archivos)

    if formato_id:
        try:
            formato = almacen.actualizar(
                formato_id, nombre=nombre.strip(), huella=huella, regla=regla_json, explicacion=explicacion
            )
        except ValueError as e:
            raise AsistenteError(str(e)) from e
    else:
        formato = almacen.guardar(
            pantalla, nombre.strip(), huella, regla_json, explicacion, _usuario_actual()
        )
    return formato_resumen(formato)


# ---------------------------------------------------------------------------
# Punto de entrada
# ---------------------------------------------------------------------------


def _respuesta_plan(
    pantalla: str, programa: Programa, por_defecto: Programa, plan: Plan, vista_previa: dict
) -> dict:
    return {
        "pantalla": pantalla,
        "programa": _serializar(programa.operaciones),
        "ia_respondio": plan.ia_respondio,
        # el modelo respondio pero el mensaje no cambio nada respecto de lo
        # que se hace sin indicaciones: la tarjeta lo dice en vez de fingir.
        "sin_indicaciones": plan.ia_respondio and programa == por_defecto,
        **vista_previa,
    }


def interpretar(pantalla: str, texto: str, archivos: dict[str, Archivo], ejecutar_llm=None) -> dict:
    """`ejecutar_llm` es solo para tests (inyectar un stub en vez del server real)."""
    _validar_pantalla(pantalla)
    if not texto.strip():
        raise AsistenteError("El pedido esta vacio.")
    faltan = _faltantes(pantalla, archivos)
    if faltan:
        return {"pantalla": pantalla, "programa": [], "faltan_archivos": faltan}
    kwargs = {"ejecutar_llm": ejecutar_llm} if ejecutar_llm is not None else {}

    if pantalla == PANTALLA_RECETAS:
        ctx = _contexto_recetas(archivos["listado"])
        plan = planificar_recetas(texto, ctx, **kwargs)
        programa = Programa(operaciones=plan.operaciones)
        por_defecto = Programa(operaciones=(Operacion("expandir_por_catalogo", {}),))
        return _respuesta_plan(pantalla, programa, por_defecto, plan, _vista_previa_recetas(programa, ctx))

    if pantalla == PANTALLA_MEDICIONES:
        lineas = _lineas_datos(archivos["datos"])
        plan = planificar_mediciones(texto, lineas, _describir_deteccion(lineas), **kwargs)
        try:
            programa = interprete_mediciones.completar(list(plan.operaciones), lineas)
            por_defecto = interprete_mediciones.completar([], lineas)
        except ValueError as e:
            raise AsistenteError(str(e)) from e
        vista_previa = _vista_previa_mediciones(programa, lineas)
        vista_previa["advertencias"] = (
            _rangos_no_usados(texto, lineas, programa) + vista_previa.get("advertencias", [])
        )
        return _respuesta_plan(pantalla, programa, por_defecto, plan, vista_previa)

    plantilla, encabezados, filas = _cargar_plantilla(archivos)
    plan = planificar_plantilla(
        texto, interprete_plantilla.lineas_con_campo(plantilla), encabezados, filas, **kwargs
    )
    programa = Programa(operaciones=plan.operaciones)
    return _respuesta_plan(
        pantalla, programa, Programa(), plan,
        _vista_previa_plantilla(programa, plantilla, encabezados, filas),
    )


def previsualizar(pantalla: str, programa_data, archivos: dict[str, Archivo]) -> dict:
    """Vista previa de un programa que el usuario edito en la tarjeta. Sin IA."""
    _validar_pantalla(pantalla)
    faltan = _faltantes(pantalla, archivos)
    if faltan:
        raise AsistenteError(f"Falta {', '.join(faltan)}.")
    programa = _programa_desde_json(programa_data)
    if pantalla == PANTALLA_RECETAS:
        vista = _vista_previa_recetas(programa, _contexto_recetas(archivos["listado"]))
    elif pantalla == PANTALLA_MEDICIONES:
        vista = _vista_previa_mediciones(programa, _lineas_datos(archivos["datos"]))
    else:
        vista = _vista_previa_plantilla(programa, *_cargar_plantilla(archivos))
    return {"pantalla": pantalla, "programa": _serializar(programa.operaciones), **vista}


def ejecutar(pantalla: str, programa_data, archivos: dict[str, Archivo], texto_usuario: str = "") -> Salida:
    _validar_pantalla(pantalla)
    faltan = _faltantes(pantalla, archivos)
    if faltan:
        raise AsistenteError(f"Falta {', '.join(faltan)}.")
    programa = _programa_desde_json(programa_data)
    ejecutor = {
        PANTALLA_RECETAS: _ejecutar_recetas,
        PANTALLA_MEDICIONES: _ejecutar_mediciones,
        PANTALLA_PLANTILLA: _ejecutar_plantilla,
    }[pantalla]
    salida = ejecutor(programa, archivos)
    dsl_log.registrar_ejecucion(
        operacion=pantalla,
        programa=_serializar(programa.operaciones),
        cantidad_archivos=salida.resumen["cantidad_archivos"],
        texto_usuario=texto_usuario,
    )
    return salida
