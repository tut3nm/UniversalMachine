"""
Generador masivo de archivos a partir de una plantilla + un listado.

Ver PLAN_GENERADOR_RECETAS.md (raiz del repo) para el diseño completo. Resumen:
un campo variable de la plantilla se marca envolviendo su valor de ejemplo
entre llaves (`{valor}`); el comentario `//` de esa misma linea nombra, en
texto libre, la columna del listado que lo reemplaza (sin mayusculas ni
acentos). La columna que ademas debe dar nombre al archivo de salida se
identifica porque su comentario contiene la frase fija "nombre del archivo".

Modulo puro (sin FastAPI ni I/O de sesion) para poder testear facil, mismo
criterio que csv_recipe.py.
"""
from __future__ import annotations

import csv
import io
import re
import unicodedata
from dataclasses import dataclass, field


_CAMPO_RE = re.compile(r"\{([^{}]*)\}")
_COMENTARIO_RE = re.compile(r"//(.*)$")
_FRASE_NOMBRE_ARCHIVO = "nombre del archivo"


def _normalizar(texto: str) -> str:
    """minusculas + sin acentos, para comparar nombres de columna/comentarios."""
    sin_acentos = unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode("ascii")
    return sin_acentos.lower().strip()


def _contiene_palabra(contenedor_norm: str, palabra_norm: str) -> bool:
    if not palabra_norm:
        return False
    return re.search(r"\b" + re.escape(palabra_norm) + r"\b", contenedor_norm) is not None


def _quitar_comentario(linea: str) -> str:
    """En los archivos finales las notas '// ...' no van: solo existen para que
    el motor sepa que columna usar, no son parte del formato que lee la maquina."""
    idx = linea.find("//")
    if idx == -1:
        return linea
    return linea[:idx].rstrip()


# ---------------------------------------------------------------------------
# Plantilla
# ---------------------------------------------------------------------------


@dataclass
class CampoVariable:
    linea_index: int
    comentario: str                # texto crudo despues de "//" en esa linea (puede ser "")
    valor_original: str            # lo que habia entre llaves
    columna_listado: str | None = None   # se resuelve en generar(); None = sin match
    es_nombre_archivo: bool = False


@dataclass
class PlantillaParseada:
    lineas: list[str]              # contenido original, linea por linea (sin fin de linea)
    campos: list[CampoVariable]
    extension: str                 # la de salida, tomada de la plantilla
    eol: str = "\n"                # fin de linea original (CRLF/LF), para reconstruir igual


def _detectar_eol(texto: str) -> str:
    """Los archivos reales de receta vienen en CRLF (los lee un equipo, no un
    editor de texto): si se reconstruye con LF nomas, puede no ser el mismo
    formato que espera la maquina."""
    return "\r\n" if "\r\n" in texto else "\n"


def parsear_plantilla(texto: str, extension: str) -> PlantillaParseada:
    eol = _detectar_eol(texto)
    lineas = texto.splitlines()
    campos: list[CampoVariable] = []
    for i, linea in enumerate(lineas):
        m = _CAMPO_RE.search(linea)
        if not m:
            continue
        m_comentario = _COMENTARIO_RE.search(linea)
        comentario = m_comentario.group(1).strip() if m_comentario else ""
        campos.append(CampoVariable(linea_index=i, comentario=comentario, valor_original=m.group(1)))
    return PlantillaParseada(lineas=lineas, campos=campos, extension=extension.lstrip("."), eol=eol)


# ---------------------------------------------------------------------------
# Listado
# ---------------------------------------------------------------------------


def _decode(raw: bytes) -> str:
    for enc in ("utf-8-sig", "cp1252", "latin-1"):
        try:
            return raw.decode(enc)
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", errors="replace")


def _sniff_delimitador(primera_linea: str) -> str:
    candidatos = {",": primera_linea.count(","), ";": primera_linea.count(";"), "\t": primera_linea.count("\t")}
    return max(candidatos, key=candidatos.get)


def leer_listado(contenido: bytes, nombre_archivo: str) -> tuple[list[str], list[dict]]:
    """Devuelve (encabezados, filas) desde .txt/.csv (delimitador auto-detectado).

    .xlsx queda fuera de alcance de la v1 (ver PLAN_GENERADOR_RECETAS.md, seccion 4.12).
    """
    ext = nombre_archivo.lower().rsplit(".", 1)[-1] if "." in nombre_archivo else ""
    if ext not in ("txt", "csv"):
        raise ValueError(
            f"Tipo de listado no soportado todavia (.{ext}). "
            "La v1 solo soporta listados .txt/.csv."
        )

    texto = _decode(contenido)
    lineas = [l for l in texto.splitlines() if l.strip() != ""]
    if not lineas:
        raise ValueError("El listado esta vacio.")

    delim = _sniff_delimitador(lineas[0])
    reader = csv.reader(lineas, delimiter=delim)
    filas_crudas = [fila for fila in reader]

    encabezados = [c.strip() for c in filas_crudas[0]]
    if len(encabezados) < 1 or all(c == "" for c in encabezados):
        raise ValueError("No se encontro una fila de encabezado en el listado.")

    filas: list[dict] = []
    for n, fila in enumerate(filas_crudas[1:], start=2):
        if len(fila) < len(encabezados):
            raise ValueError(
                f"La fila {n} del listado tiene menos columnas ({len(fila)}) "
                f"que el encabezado ({len(encabezados)})."
            )
        filas.append({encabezados[j]: fila[j].strip() for j in range(len(encabezados))})

    return encabezados, filas


# ---------------------------------------------------------------------------
# Generacion
# ---------------------------------------------------------------------------


@dataclass
class RegistroGenerado:
    nombre_archivo: str
    contenido: str
    fila_origen: int               # numero de fila del listado (1-based, sin contar encabezado)


@dataclass
class ResultadoGeneracion:
    archivos: list[RegistroGenerado] = field(default_factory=list)
    lineas_ignoradas: list[int] = field(default_factory=list)   # indices de linea sin match
    columnas_sin_uso: list[str] = field(default_factory=list)


def _resolver_columna(campo: CampoVariable, encabezados_norm: dict[str, str]) -> str | None:
    """Busca, entre los encabezados normalizados, cual aparece mencionado en el
    comentario del campo. Devuelve la columna (nombre original) si matchea
    exactamente una, None si no matchea ninguna o matchea mas de una."""
    comentario_norm = _normalizar(campo.comentario)
    if not comentario_norm:
        return None
    encontradas = [
        original for original, norm in encabezados_norm.items()
        if _contiene_palabra(comentario_norm, norm)
    ]
    if len(encontradas) != 1:
        return None
    return encontradas[0]


def generar(plantilla: PlantillaParseada, encabezados: list[str], filas: list[dict]) -> ResultadoGeneracion:
    encabezados_norm = {h: _normalizar(h) for h in encabezados}

    campos_resueltos: list[CampoVariable] = []
    for campo in plantilla.campos:
        columna = _resolver_columna(campo, encabezados_norm)
        es_nombre_archivo = columna is not None and _FRASE_NOMBRE_ARCHIVO in _normalizar(campo.comentario)
        campos_resueltos.append(
            CampoVariable(
                linea_index=campo.linea_index,
                comentario=campo.comentario,
                valor_original=campo.valor_original,
                columna_listado=columna,
                es_nombre_archivo=es_nombre_archivo,
            )
        )

    campos_nombre_archivo = [c for c in campos_resueltos if c.es_nombre_archivo]
    if len(campos_nombre_archivo) != 1:
        raise ValueError(
            "La plantilla debe tener exactamente un campo {...} cuyo comentario diga "
            f"'{_FRASE_NOMBRE_ARCHIVO}' (encontrados: {len(campos_nombre_archivo)})."
        )
    campo_nombre_archivo = campos_nombre_archivo[0]

    lineas_ignoradas = sorted(c.linea_index for c in campos_resueltos if c.columna_listado is None)
    columnas_usadas = {c.columna_listado for c in campos_resueltos if c.columna_listado is not None}
    columnas_sin_uso = [h for h in encabezados if h not in columnas_usadas]

    lineas_base = list(plantilla.lineas)
    for campo in campos_resueltos:
        # la nota "// ..." no va en el archivo final, matcheo o no matcheo columna
        lineas_base[campo.linea_index] = _quitar_comentario(lineas_base[campo.linea_index])
        if campo.columna_listado is None:
            lineas_base[campo.linea_index] = lineas_base[campo.linea_index].replace(
                "{" + campo.valor_original + "}", campo.valor_original
            )

    campos_variables = [c for c in campos_resueltos if c.columna_listado is not None]

    resultado = ResultadoGeneracion(lineas_ignoradas=lineas_ignoradas, columnas_sin_uso=columnas_sin_uso)
    nombres_usados: dict[str, int] = {}

    for i, fila in enumerate(filas, start=1):
        lineas_fila = list(lineas_base)
        for campo in campos_variables:
            valor = fila.get(campo.columna_listado, "")
            lineas_fila[campo.linea_index] = lineas_fila[campo.linea_index].replace(
                "{" + campo.valor_original + "}", valor
            )

        base_nombre = fila.get(campo_nombre_archivo.columna_listado, "").strip()
        if not base_nombre:
            raise ValueError(f"La fila {i} del listado no tiene valor para el nombre de archivo.")

        contador = nombres_usados.get(base_nombre, 0) + 1
        nombres_usados[base_nombre] = contador
        sufijo = "" if contador == 1 else f"_{contador}"
        nombre_archivo = f"{base_nombre}{sufijo}.{plantilla.extension}"

        resultado.archivos.append(
            RegistroGenerado(
                nombre_archivo=nombre_archivo,
                contenido=plantilla.eol.join(lineas_fila),
                fila_origen=i,
            )
        )

    return resultado
