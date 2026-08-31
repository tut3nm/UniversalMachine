"""Seed y migración de datos al activar una máquina por primera vez.
Extraído de App._seed_or_migrate / App._migrate_legacy_232 (Nivel 3.1) para
poder probarlo sin instanciar la ventana."""

from __future__ import annotations

import csv
import os

import paths
from io_seguro import copiar_atomico
from datastore import DataStore
from metadata import Sidecar
from profile import Profile

LEGACY_REVIEW_LABEL = "Configurador232_RevisadoNoDuplicado"


def seed_or_migrate(profile: Profile, path_original: str,
                     path_actual: str, path_meta: str) -> None:
    legacy = os.path.join(paths.app_base_dir(), "datos232")
    if (profile.id == "232" and os.path.isdir(legacy)
            and os.path.exists(os.path.join(legacy, "actual.csv"))):
        migrate_legacy_232(legacy, profile, path_original, path_actual, path_meta)
        return
    if profile.archivo_inicial:
        src = paths.resource_path(profile.archivo_inicial)
        if os.path.exists(src):
            copiar_atomico(src, path_original)
            copiar_atomico(path_original, path_actual)
            return
    empty = DataStore(profile, [])
    empty.save(path_original)
    empty.save(path_actual)


def migrate_legacy_232(legacy: str, profile: Profile, path_original: str,
                        path_actual: str, path_meta: str) -> None:
    old_orig = os.path.join(legacy, "original.csv")
    old_act = os.path.join(legacy, "actual.csv")
    if os.path.exists(old_orig):
        copiar_atomico(old_orig, path_original)
    with open(old_act, encoding="utf-8-sig", newline="") as f:
        rows = list(csv.reader(f))
    sc = Sidecar.load(path_meta)
    if len(rows) > 7 and rows[7] and rows[7][0].strip() == LEGACY_REVIEW_LABEL:
        codes, marks = rows[2][1:], rows[7][1:]
        for code, m in zip(codes, marks):
            if str(m).strip() == "1" and code.strip():
                sc.set(code.strip(), "no_duplicado", True)
        sc.save()
    store = DataStore.load(old_act, profile)
    store.save(path_actual)
    if not os.path.exists(path_original):
        store.save(path_original)
