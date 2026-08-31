"""Versión de la aplicación (Nivel 3.4 del plan de mejoras).

`build.bat` reemplaza FECHA_COMPILACION por la fecha real al empaquetar el
.exe (ver ese script); en desarrollo queda "sin compilar"."""

APP_VERSION = "0.4.0"
FECHA_COMPILACION = "sin compilar"

try:
    # build.bat genera este archivo (gitignored) justo antes de compilar con
    # PyInstaller, con la fecha real de compilación. En desarrollo no existe
    # y se usa el valor por defecto de arriba.
    from _build_info import FECHA_COMPILACION  # type: ignore  # noqa: F811
except ImportError:
    pass


def version_completa() -> str:
    return f"{APP_VERSION} ({FECHA_COMPILACION})"
