"""
profile.py
==========
Perfil de máquina: describe el formato de un archivo de parámetros para que el
motor genérico (datastore.py) sepa cómo leerlo y reconstruirlo byte por byte,
sin tener el formato "cableado" en el código.

Un perfil es un archivo JSON (ver profiles/maquina_232.json). Este módulo lo
carga, lo valida y lo expone como objetos cómodos de usar.

Conceptos:
  * orientacion = "columnas": cada registro es una COLUMNA (caso 232). La
    columna 0 tiene etiquetas; cada fila fija/índice/campo vive en una fila.
  * orientacion = "filas": cada registro es una FILA (CSV normal). Hay una
    fila de encabezado y cada campo es una columna. (Soportado por el motor;
    todavía sin un archivo real de planta para validarlo.)
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field

# Nombre de línea legible -> caracteres reales
FIN_DE_LINEA = {"CRLF": "\r\n", "LF": "\n", "CR": "\r"}

TIPOS_VALIDOS = {"texto", "entero", "entero_ceros", "decimal"}
ROLES_VALIDOS = {"clave", "parametro"}
ORIENTACIONES = {"columnas", "filas"}


class ProfileError(ValueError):
    """El perfil JSON es inválido o incompleto."""


@dataclass
class Campo:
    nombre_interno: str
    rol: str                       # "clave" | "parametro"
    tipo: str                      # "texto" | "entero" | "entero_ceros" | "decimal"
    titulo_ui: str
    etiqueta: str = ""             # texto de la celda-etiqueta (col0 o encabezado)
    fila: int | None = None        # ubicación si orientacion == "columnas"
    columna: int | None = None     # ubicación si orientacion == "filas"
    min: float | None = None
    max: float | None = None
    default: object = None
    visible: bool = True           # False = campo "oculto": viaja con cada
                                    # registro (crece/achica con alta/baja)
                                    # pero no se muestra ni se edita en la UI.
    formato: dict = field(default_factory=dict)
    # formato (según tipo):
    #   entero_ceros: {"ancho": N}                 -> rellena con ceros a la izq.
    #   decimal:      {"separador_decimal": ",",   -> "." o "," al formatear
    #                  "decimales": N,              -> cantidad fija de decimales
    #                  "separador_miles": ""}       -> "." "," " " o "" (sin miles)

    @property
    def es_clave(self) -> bool:
        return self.rol == "clave"

    @property
    def es_numerico(self) -> bool:
        return self.tipo in ("entero", "entero_ceros", "decimal")


@dataclass
class Profile:
    id: str
    nombre: str
    descripcion: str
    archivo_inicial: str            # archivo de muestra embebido para sembrar (o "")
    # archivo
    extension: str
    delimitador: str
    encoding: str
    bom: bool
    fin_de_linea: str              # ya resuelto a caracteres reales
    orientacion: str
    # estructura
    columna_etiquetas: int
    primera_columna_datos: int
    filas_fijas: list[dict]
    fila_indice: dict | None
    # encabezado (solo orientacion == "filas")
    fila_encabezado: int
    primera_fila_datos: int
    # campos
    campos: list[Campo]
    features: dict = field(default_factory=dict)
    ruta: str = ""
    version_esquema: int = 1  # versión del FORMATO del perfil JSON (Nivel
    # 3.4), no de la app: permite migrar perfiles viejos si el esquema
    # cambia en el futuro sin romper los que ya existen en planta.

    # -- Accesos cómodos -------------------------------------------------------
    def campo_clave(self) -> Campo:
        for c in self.campos:
            if c.es_clave:
                return c
        raise ProfileError("El perfil no define un campo con rol 'clave'.")

    def parametros(self) -> list[Campo]:
        return [c for c in self.campos if c.rol == "parametro"]

    def campos_visibles(self) -> list[Campo]:
        """Clave + parámetros visibles, en el orden del perfil (para la tabla
        y los diálogos). Los campos con visible=False no se listan acá: viajan
        con cada registro (para no romper el round-trip byte-perfecto) pero
        nunca se muestran ni se editan desde la UI."""
        return [c for c in self.campos if c.visible]

    def parametros_visibles(self) -> list[Campo]:
        return [c for c in self.campos if c.rol == "parametro" and c.visible]

    def campo_por_nombre(self, nombre: str) -> Campo | None:
        for c in self.campos:
            if c.nombre_interno == nombre:
                return c
        return None

    # -- Features --------------------------------------------------------------
    def placeholder_regex(self) -> re.Pattern | None:
        ph = self.features.get("placeholder")
        if ph and ph.get("patron"):
            return re.compile(ph["patron"])
        return None

    def placeholder_template(self) -> str | None:
        ph = self.features.get("placeholder")
        return ph.get("generar") if ph else None

    def duplicados_config(self) -> dict | None:
        return self.features.get("duplicados")

    # -- Carga -----------------------------------------------------------------
    @classmethod
    def load(cls, path: str) -> "Profile":
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except json.JSONDecodeError as exc:
            raise ProfileError(f"JSON inválido en {path}: {exc}") from exc
        prof = cls.from_dict(data)
        prof.ruta = path
        return prof

    @classmethod
    def from_dict(cls, data: dict) -> "Profile":
        def req(d: dict, key: str, ctx: str):
            if key not in d:
                raise ProfileError(f"Falta la clave obligatoria '{key}' en {ctx}.")
            return d[key]

        arch = req(data, "archivo", "el perfil")
        est = req(data, "estructura", "el perfil")

        orientacion = arch.get("orientacion", "columnas")
        if orientacion not in ORIENTACIONES:
            raise ProfileError(f"orientacion '{orientacion}' no válida "
                               f"(usar una de {sorted(ORIENTACIONES)}).")

        fdl_nombre = arch.get("fin_de_linea", "CRLF")
        if fdl_nombre not in FIN_DE_LINEA:
            raise ProfileError(f"fin_de_linea '{fdl_nombre}' no válido "
                               f"(usar CRLF, LF o CR).")

        campos = []
        for i, cd in enumerate(req(data, "campos", "el perfil")):
            campos.append(_campo_from_dict(cd, i, orientacion))

        prof = cls(
            id=str(req(data, "id", "el perfil")),
            nombre=data.get("nombre", str(data.get("id", ""))),
            descripcion=data.get("descripcion", ""),
            archivo_inicial=data.get("archivo_inicial", ""),
            extension=arch.get("extension", "csv").lstrip("."),
            delimitador=arch.get("delimitador", ","),
            encoding=arch.get("encoding", "utf-8"),
            bom=bool(arch.get("bom", False)),
            fin_de_linea=FIN_DE_LINEA[fdl_nombre],
            orientacion=orientacion,
            columna_etiquetas=int(est.get("columna_etiquetas", 0)),
            primera_columna_datos=int(est.get("primera_columna_datos", 1)),
            filas_fijas=list(est.get("filas_fijas", [])),
            fila_indice=est.get("fila_indice"),
            fila_encabezado=int(est.get("fila_encabezado", 0)),
            primera_fila_datos=int(est.get("primera_fila_datos", 1)),
            campos=campos,
            features=data.get("features", {}) or {},
            version_esquema=int(data.get("version", 1)),
        )
        prof._validar()
        return prof

    # -- Validación ------------------------------------------------------------
    def _validar(self) -> None:
        if not any(c.es_clave for c in self.campos):
            raise ProfileError("El perfil debe tener exactamente un campo con "
                               "rol 'clave'.")
        if sum(1 for c in self.campos if c.es_clave) > 1:
            raise ProfileError("El perfil tiene más de un campo con rol 'clave'.")

        nombres = [c.nombre_interno for c in self.campos]
        if len(nombres) != len(set(nombres)):
            raise ProfileError("Hay nombres_interno de campo repetidos.")

        self._validar_placeholder()
        self._validar_campos()

        if self.orientacion == "columnas":
            self._validar_columnas()

    def _validar_placeholder(self) -> None:
        """Compila y valida el regex/plantilla de la feature 'placeholder'
        ACÁ, al cargar el perfil — antes se compilaba recién en el primer
        uso (placeholder_regex(), llamado cada vez que se refresca la
        tabla), así que un patrón inválido no fallaba con un ProfileError
        claro al arrancar, sino con un re.error crudo en medio de la UI."""
        ph = self.features.get("placeholder")
        if not ph:
            return
        patron = ph.get("patron")
        if patron:
            try:
                re.compile(patron)
            except re.error as exc:
                raise ProfileError(
                    f"El patrón de placeholder '{patron}' no es un regex "
                    f"válido: {exc}") from exc
        generar = ph.get("generar")
        if generar:
            try:
                generar.format(n=0)
            except (KeyError, IndexError, ValueError) as exc:
                raise ProfileError(
                    f"La plantilla 'generar' del placeholder ('{generar}') "
                    f"no es válida: {exc}") from exc

    def _validar_campos(self) -> None:
        """Coherencia de min/max/default/formato de cada campo — antes no se
        validaba nada de esto: un perfil con min > max, un default fuera de
        rango, o un 'ancho'/'decimales' inválido solo se notaba al usarlo
        (o ni eso, si el dato nunca se editaba)."""
        for c in self.campos:
            if c.min is not None and c.max is not None and c.min > c.max:
                raise ProfileError(
                    f"El campo '{c.nombre_interno}': min ({c.min}) no puede "
                    f"ser mayor que max ({c.max}).")

            if c.default is not None and c.es_numerico:
                try:
                    default_num = float(c.default)
                except (TypeError, ValueError):
                    raise ProfileError(
                        f"El campo '{c.nombre_interno}': default "
                        f"({c.default!r}) no es compatible con el tipo "
                        f"'{c.tipo}'.")
                if c.min is not None and default_num < c.min:
                    raise ProfileError(
                        f"El campo '{c.nombre_interno}': default "
                        f"({c.default}) es menor que min ({c.min}).")
                if c.max is not None and default_num > c.max:
                    raise ProfileError(
                        f"El campo '{c.nombre_interno}': default "
                        f"({c.default}) es mayor que max ({c.max}).")

            if c.tipo == "entero_ceros" and c.formato and "ancho" in c.formato:
                ancho = c.formato["ancho"]
                if not isinstance(ancho, int) or isinstance(ancho, bool) or ancho <= 0:
                    raise ProfileError(
                        f"El campo '{c.nombre_interno}': formato.ancho debe "
                        f"ser un entero positivo (viene {ancho!r}).")

            if c.tipo == "decimal" and c.formato and "decimales" in c.formato:
                dec = c.formato["decimales"]
                if not isinstance(dec, int) or isinstance(dec, bool) or dec < 0:
                    raise ProfileError(
                        f"El campo '{c.nombre_interno}': formato.decimales "
                        f"debe ser un entero >= 0 (viene {dec!r}).")

    def _validar_columnas(self) -> None:
        """Verifica que las filas 0..max estén todas cubiertas exactamente una
        vez por filas_fijas / fila_indice / campos (sin huecos ni choques)."""
        ocupadas: dict[int, str] = {}

        def ocupar(fila, quien: str):
            if fila is None:
                raise ProfileError(f"{quien}: falta el número de 'fila' "
                                   "(obligatorio en orientacion 'columnas').")
            if not isinstance(fila, int) or isinstance(fila, bool):
                raise ProfileError(f"{quien}: 'fila' debe ser un número entero "
                                   f"(viene {fila!r}).")
            if fila in ocupadas:
                raise ProfileError(
                    f"La fila {fila} está definida por dos cosas: "
                    f"{ocupadas[fila]} y {quien}.")
            ocupadas[fila] = quien

        for ff in self.filas_fijas:
            ocupar(ff.get("fila"), "una fila fija")
        if self.fila_indice:
            ocupar(self.fila_indice.get("fila"), "la fila índice")
        for c in self.campos:
            ocupar(c.fila, f"el campo '{c.nombre_interno}'")

        max_fila = max(ocupadas)
        faltantes = [r for r in range(max_fila + 1) if r not in ocupadas]
        if faltantes:
            raise ProfileError(
                f"Faltan definir las filas {faltantes} (entre 0 y {max_fila}). "
                "Toda fila debe ser una fila fija, la fila índice o un campo.")


def _campo_from_dict(cd: dict, idx: int, orientacion: str) -> Campo:
    if "nombre_interno" not in cd:
        raise ProfileError(f"El campo #{idx + 1} no tiene 'nombre_interno'.")
    tipo = cd.get("tipo", "texto")
    if tipo not in TIPOS_VALIDOS:
        raise ProfileError(f"tipo '{tipo}' no válido en el campo "
                           f"'{cd['nombre_interno']}' (usar {sorted(TIPOS_VALIDOS)}).")
    rol = cd.get("rol", "parametro")
    if rol not in ROLES_VALIDOS:
        raise ProfileError(f"rol '{rol}' no válido en el campo "
                           f"'{cd['nombre_interno']}' (usar {sorted(ROLES_VALIDOS)}).")
    return Campo(
        nombre_interno=cd["nombre_interno"],
        rol=rol,
        tipo=tipo,
        titulo_ui=cd.get("titulo_ui", cd["nombre_interno"]),
        etiqueta=cd.get("etiqueta", ""),
        fila=cd.get("fila"),
        columna=cd.get("columna"),
        min=cd.get("min"),
        max=cd.get("max"),
        default=cd.get("default"),
        visible=bool(cd.get("visible", True)),
        formato=dict(cd.get("formato", {}) or {}),
    )
