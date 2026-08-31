"""
validacion.py
=============
Validación de valores de un registro contra las reglas del perfil (rango
min/max de cada campo numérico). Independiente de la UI a propósito: antes,
esta validación solo existía "a mano" dentro de RecordDialog._on_ok (edición
manual en app.py) y la importación desde Excel aplicaba los cambios sin
ningún control de rango — un typo en el Excel (p. ej. una velocidad de 3500
en vez de 350) entraba sin resistencia al archivo que se sube a la máquina.

Este módulo centraliza esa regla para que ambos caminos (edición manual e
importación) validen exactamente igual.
"""

from __future__ import annotations

from dataclasses import dataclass

from profile import Campo, Profile


@dataclass
class ErrorValidacion:
    campo: str          # nombre_interno
    titulo_ui: str
    mensaje: str


def _fmt(n) -> str:
    return str(int(n)) if float(n).is_integer() else str(n)


def validar_valor_numerico(campo: Campo, valor) -> str | None:
    """Valida un valor YA TIPADO (int/float) de un campo numérico contra el
    min/max declarado en el perfil. Devuelve un mensaje de error en español
    listo para mostrar, o None si el valor es válido (o si `valor` es None,
    es decir "sin dato": no hay nada que validar)."""
    if valor is None:
        return None
    if campo.min is not None and valor < campo.min:
        return f"«{campo.titulo_ui}» no puede ser menor que {_fmt(campo.min)} (viene {_fmt(valor)})."
    if campo.max is not None and valor > campo.max:
        return f"«{campo.titulo_ui}» no puede ser mayor que {_fmt(campo.max)} (viene {_fmt(valor)})."
    return None


def parsear_valor_campo(campo: Campo, texto: str) -> tuple[object, str | None]:
    """Convierte el texto crudo de UN campo a su valor tipado, validando
    rango si corresponde (Nivel 4.8: edición en línea y edición masiva
    reutilizan exactamente esta lógica, no una versión aparte). Devuelve
    (valor, None) si es válido, o (None, mensaje_de_error) si no. No valida
    duplicados de clave — depende del DataStore y de qué índice se está
    editando, que el llamador ya conoce."""
    texto = texto.strip()
    if campo.es_clave:
        if not texto:
            return None, f"«{campo.titulo_ui}» no puede estar vacío."
        return texto, None
    if campo.es_numerico:
        if texto == "":
            return (campo.default if campo.default is not None else 0), None
        try:
            texto_norm = texto.replace(",", ".")
            valor = float(texto_norm) if campo.tipo == "decimal" \
                else int(round(float(texto_norm)))
        except ValueError:
            return None, f"«{campo.titulo_ui}» debe ser un número."
        error_rango = validar_valor_numerico(campo, valor)
        if error_rango:
            return None, error_rango
        return valor, None
    return texto, None


def validar_valores_de_registro(profile: Profile, valores: dict) -> list[ErrorValidacion]:
    """Valida los campos numéricos VISIBLES de `valores` (dict
    nombre_interno -> valor ya tipado) contra sus rangos min/max. No valida
    la clave (vacía/duplicada) — eso depende del DataStore y cada llamador
    ya lo resuelve con su propio contexto (RecordDialog conoce edit_index;
    la importación garantiza códigos únicos por construcción)."""
    errores: list[ErrorValidacion] = []
    for campo in profile.campos_visibles():
        if campo.es_clave or not campo.es_numerico:
            continue
        if campo.nombre_interno not in valores:
            continue
        mensaje = validar_valor_numerico(campo, valores[campo.nombre_interno])
        if mensaje:
            errores.append(ErrorValidacion(campo.nombre_interno, campo.titulo_ui, mensaje))
    return errores
