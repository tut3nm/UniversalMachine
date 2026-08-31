"""
io_seguro.py
============
Escritura atómica de archivos de texto/JSON en disco.

Por qué existe: escribir directo sobre el archivo destino (`open(path, "w")`)
lo trunca a cero antes de volcar el contenido nuevo. Si el proceso muere en
ese instante (corte de luz, cuelgue, kill del proceso, antivirus bloqueando
el archivo a mitad de escritura), el archivo queda vacío o cortado — y en
esta aplicación ese archivo es el que se sube al HMI de la máquina.

La solución estándar: escribir el contenido completo a un archivo temporal
en la MISMA carpeta (mismo volumen, requisito para que el reemplazo sea
atómico), forzar el volcado a disco físico, y recién ahí reemplazar el
archivo final de un solo paso con `os.replace()` (atómico en NTFS/POSIX).
Si algo falla en el medio, el archivo original queda intacto.

Reintento de `os.replace()`: en Windows, un antivirus (o un indexador de
archivos) puede tener el archivo destino abierto por una fracción de
segundo justo cuando se intenta reemplazarlo, lo que hace fallar
`os.replace()` con `PermissionError` (WinError 32, "being used by another
process") de forma transitoria — se reprodujo en la práctica bajo uso
intenso de E/S. Un solo reintento con una espera breve resuelve la enorme
mayoría de estos casos sin esconder un fallo real (si el segundo intento
también falla, el error se propaga tal cual)."""

from __future__ import annotations

import os
import tempfile
import time

_REINTENTOS_REPLACE = 3
_ESPERA_ENTRE_REINTENTOS_SEG = 0.05


def _replace_con_reintento(origen: str, destino: str) -> None:
    for intento in range(_REINTENTOS_REPLACE):
        try:
            os.replace(origen, destino)
            return
        except PermissionError:
            if intento == _REINTENTOS_REPLACE - 1:
                raise
            time.sleep(_ESPERA_ENTRE_REINTENTOS_SEG * (intento + 1))


def escribir_atomico(path: str, contenido: str, encoding: str = "utf-8",
                      newline: str = "") -> None:
    """Escribe `contenido` en `path` de forma atómica: el archivo destino
    queda o bien con el contenido COMPLETO nuevo, o bien sin ningún cambio —
    nunca a medio escribir.

    `newline=""` (default) reproduce el comportamiento de `open(..., "w",
    newline="")` que ya usa el resto de la app: no traduce los `\\n`/`\\r\\n`
    que ya vienen en `contenido`, para no interferir con el fin de línea
    exacto que espera el perfil de la máquina.
    """
    carpeta = os.path.dirname(os.path.abspath(path)) or "."
    os.makedirs(carpeta, exist_ok=True)

    fd, tmp_path = tempfile.mkstemp(prefix=".tmp-", dir=carpeta)
    try:
        with os.fdopen(fd, "w", encoding=encoding, newline=newline) as f:
            f.write(contenido)
            f.flush()
            os.fsync(f.fileno())
        _replace_con_reintento(tmp_path, path)
    except BaseException:
        # Si algo falló antes del replace, no dejamos basura ni tocamos el
        # archivo original: se borra el temporal y se relanza el error para
        # que el llamador decida cómo avisar al usuario.
        try:
            os.remove(tmp_path)
        except OSError:
            pass
        raise


def verificar_contenido(path: str, esperado: str, encoding: str = "utf-8") -> bool:
    """Relee `path` desde disco y confirma que su contenido es exactamente
    `esperado`. Uso típico: después de guardar, releer y comparar contra lo
    que el motor tiene en memoria — confirma que el guardado no solo 'no
    lanzó una excepción', sino que el archivo en disco quedó tal cual se
    esperaba (protege contra interferencia externa: antivirus, discos de
    red intermitentes, sectores dañados, etc.).

    Devuelve False (no lanza) si el archivo no se puede leer, para que el
    llamador lo trate como un fallo de guardado más."""
    try:
        with open(path, "r", encoding=encoding, newline="") as f:
            en_disco = f.read()
    except OSError:
        return False
    return en_disco == esperado


def escribir_bytes_atomico(path: str, contenido: bytes) -> None:
    """Variante binaria de `escribir_atomico`, para casos donde el contenido
    ya viene codificado (p. ej. para controlar el encoding exacto aparte)."""
    carpeta = os.path.dirname(os.path.abspath(path)) or "."
    os.makedirs(carpeta, exist_ok=True)

    fd, tmp_path = tempfile.mkstemp(prefix=".tmp-", dir=carpeta)
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(contenido)
            f.flush()
            os.fsync(f.fileno())
        _replace_con_reintento(tmp_path, path)
    except BaseException:
        try:
            os.remove(tmp_path)
        except OSError:
            pass
        raise


def copiar_atomico(origen: str, destino: str) -> None:
    """Equivalente a shutil.copyfile(origen, destino) pero sin dejar
    `destino` a medio escribir si el proceso se corta en el medio. Se usa
    para todo lo que termine escribiendo actual.<ext> u original.<ext> por
    copia directa de bytes (restaurar, sembrar una máquina nueva, migrar
    datos legado)."""
    with open(origen, "rb") as f:
        contenido = f.read()
    escribir_bytes_atomico(destino, contenido)
