"""Pone app/core/ en sys.path para poder importar sus módulos con imports
planos (`from profile import Profile`, etc.) tal cual están escritos en
máquina232/src/ — no se reescriben imports al copiarlos (ver PLAN_WEBAPP.md,
"Reutilización de máquina232/src/"). Se importa este módulo primero, antes
que cualquier router o service que dependa de core/."""

from __future__ import annotations

import os
import sys

_CORE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "core")
if _CORE_DIR not in sys.path:
    sys.path.insert(0, _CORE_DIR)
