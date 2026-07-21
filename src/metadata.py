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


class Sidecar:
    def __init__(self, path: str, data: dict | None = None):
        self.path = path
        self._flags: dict[str, dict] = (data or {}).get("flags", {})

    @classmethod
    def load(cls, path: str) -> "Sidecar":
        if os.path.exists(path):
            try:
                with open(path, "r", encoding="utf-8") as f:
                    return cls(path, json.load(f))
            except (json.JSONDecodeError, OSError):
                pass  # sidecar corrupto o ilegible: arrancamos vacío
        return cls(path, {})

    def save(self) -> None:
        # Compactamos: sacamos claves sin ningún flag activo.
        clean = {k: v for k, v in self._flags.items() if any(v.values())}
        with open(self.path, "w", encoding="utf-8") as f:
            json.dump({"flags": clean}, f, ensure_ascii=False, indent=2)

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
