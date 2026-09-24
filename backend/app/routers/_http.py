"""Helpers HTTP compartidos entre routers."""
from __future__ import annotations

from urllib.parse import quote


def content_disposition(nombre: str) -> str:
    """Header `Content-Disposition` para una descarga con nombre arbitrario.

    Un `filename="..."` crudo no soporta caracteres fuera de latin-1 (ej.
    acentos, "€") ni comillas embebidas sin romper el header. Se manda un
    nombre ASCII de respaldo (para clientes viejos) + el nombre real en
    UTF-8 via `filename*` (RFC 5987), que los navegadores modernos
    prefieren."""
    ascii_seguro = nombre.encode("ascii", "replace").decode("ascii").replace('"', "_").replace("?", "_")
    return f"attachment; filename=\"{ascii_seguro}\"; filename*=UTF-8''{quote(nombre)}"
