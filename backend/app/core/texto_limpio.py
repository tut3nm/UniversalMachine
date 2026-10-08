"""Limpieza de texto de los archivos de máquina: saca acentos y diéresis
(``ö`` -> ``o``, ``á`` -> ``a``) y deja todo lo demás tal cual — mayúsculas,
minúsculas, símbolos raros (``°``, ``Ø``, ``µ``) y espacios.

``ñ`` y ``ç`` se conservan a propósito: son letras propias, no una letra con
adorno, y sacarles la marca cambia la palabra ("año" -> "ano").

La limpieza es idempotente y corre sobre celdas, así que se puede aplicar en
cada apertura del archivo sin acumular cambios.
"""

from __future__ import annotations

import unicodedata

_LETRAS_PROPIAS = frozenset("ñÑçÇ")


def quitar_acentos(texto: str) -> str:
    """Devuelve `texto` sin acentos ni diéresis."""
    if texto.isascii():
        return texto
    salida: list[str] = []
    for ch in texto:
        if ch in _LETRAS_PROPIAS or ch.isascii():
            salida.append(ch)
            continue
        base = unicodedata.normalize("NFD", ch)
        salida.append("".join(c for c in base if unicodedata.category(c) != "Mn"))
    return "".join(salida)


def limpiar_grid(grid: list[list[str]]) -> int:
    """Limpia in situ todas las celdas de la grilla. Devuelve cuántas celdas
    cambiaron (para avisarle al operario qué se tocó)."""
    cambiadas = 0
    for fila in grid:
        for j, celda in enumerate(fila):
            limpia = quitar_acentos(celda)
            if limpia != celda:
                fila[j] = limpia
                cambiadas += 1
    return cambiadas
