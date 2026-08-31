"""
metadata.py
===========
Metadatos propios de la app, guardados en un archivo sidecar aparte
(datos/<id>/meta.json). NO son parte del archivo de la máquina: acá va, por
ejemplo, la marca "el usuario revisó este código y NO es un duplicado".

Se keyea por el valor de la clave del registro (el código de pieza), no por
posición, para que sobreviva a reordenamientos y altas/bajas.

Formato del archivo:
    {
      "flags": {
        "004981007309": {"no_duplicado": true},
        "A121538":      {"no_duplicado": true}
      }
    }
"""

from __future__ import annotations

import json
import os
from datetime import datetime

from io_seguro import escribir_atomico


class Sidecar:
    def __init__(self, path: str, data: dict | None = None):
        self.path = path
        self._flags: dict[str, dict] = (data or {}).get("flags", {})
        # Se completan en load() SOLO si el archivo estaba corrupto/ilegible.
        # El llamador (app.py) los revisa para avisarle al usuario en vez de
        # perder las marcas de "no es duplicado" en silencio.
        self.recuperado_de_corrupcion: bool = False
        self.motivo_corrupcion: str | None = None
        self.ruta_respaldo_corrupto: str | None = None

    @classmethod
    def load(cls, path: str) -> "Sidecar":
        if not os.path.exists(path):
            return cls(path, {})
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            if not isinstance(data, dict) or not isinstance(data.get("flags", {}), dict):
                # JSON sintácticamente válido pero con una forma inesperada
                # (p. ej. una lista en la raíz): se trata igual que un
                # archivo corrupto, no se intenta adivinar qué quiso decir.
                raise ValueError(
                    f"formato inesperado: se esperaba un objeto con 'flags', "
                    f"se encontró {type(data).__name__}")
            return cls(path, data)
        except (json.JSONDecodeError, OSError, ValueError) as exc:
            # Antes: se descartaba en silencio y se arrancaba vacío, sin que
            # el usuario se enterara de que perdió todas sus marcas de
            # "no es duplicado". Ahora: se aísla el archivo dañado a un
            # costado (por si se puede rescatar algo a mano) y se deja
            # constancia del motivo para que la UI pueda avisar.
            sc = cls(path, {})
            sc.recuperado_de_corrupcion = True
            sc.motivo_corrupcion = str(exc)
            sc.ruta_respaldo_corrupto = cls._aislar_archivo_corrupto(path)
            return sc

    @staticmethod
    def _aislar_archivo_corrupto(path: str) -> str | None:
        """Renombra el archivo dañado a `<path>.corrupto-<timestamp>` en vez
        de sobreescribirlo cuando se guarde el sidecar vacío. Devuelve la
        ruta del respaldo, o None si ni siquiera se pudo renombrar (en ese
        caso el archivo corrupto original queda donde estaba)."""
        destino = f"{path}.corrupto-{datetime.now():%Y%m%d-%H%M%S}"
        try:
            os.replace(path, destino)
            return destino
        except OSError:
            return None

    def save(self, claves_validas: "set[str] | None" = None) -> int:
        """Guarda el sidecar. Si se pasa `claves_validas` (las claves que
        existen HOY en el catálogo), además de compactar los flags sin
        ningún valor activo, descarta las marcas de claves que ya no
        existen — p. ej. un registro borrado hace tiempo cuyo flag
        'no_duplicado' quedaba pegado para siempre (metadatos huérfanos).
        Devuelve cuántas claves se limpiaron por esa razón (0 si no se pasó
        `claves_validas`, o si no había huérfanas)."""
        flags = self._flags
        limpiadas = 0
        if claves_validas is not None:
            huerfanas = [k for k in flags if k not in claves_validas]
            limpiadas = len(huerfanas)
            flags = {k: v for k, v in flags.items() if k in claves_validas}

        # Compactamos: sacamos claves sin ningún flag activo.
        clean = {k: v for k, v in flags.items() if any(v.values())}
        contenido = json.dumps({"flags": clean}, ensure_ascii=False, indent=2)
        escribir_atomico(self.path, contenido, encoding="utf-8")
        if claves_validas is not None:
            self._flags = clean
        return limpiadas

    # -- Acceso a flags --------------------------------------------------------
    def get(self, key: str, flag: str, default=False):
        return self._flags.get(key, {}).get(flag, default)

    def set(self, key: str, flag: str, value=True) -> None:
        self._flags.setdefault(key, {})[flag] = value

    def keys_with(self, flag: str) -> frozenset:
        """Todas las claves cuyo `flag` está en True."""
        return frozenset(k for k, v in self._flags.items() if v.get(flag))

    def rename_key(self, old: str, new: str) -> None:
        """Si un código cambia de nombre, mover sus flags con él."""
        if old in self._flags and old != new:
            self._flags[new] = self._flags.pop(old)
