# Universal Machine

Monorepo con las herramientas de planta:

- [`máquina232/`](máquina232/README.md) — Configurador de Parámetros de
  Planta (app de escritorio, Tkinter). Ver su propio README para uso,
  arquitectura y el [plan de mejoras](máquina232/PLAN_MEJORAS.md) en curso.
- [`Diagramadora/`](Diagramadora/) — Conversor Universal de Excel/CSV con
  IA local (llama.cpp embebido) y editor de recetas.
- `front/` / `backend/` — nuevo sistema web (FastAPI + React) que unifica
  las dos apps de arriba; ver [`PLAN_WEBAPP.md`](PLAN_WEBAPP.md)
  (implementación aún no iniciada). Las dos apps de escritorio de arriba
  no dependen de ellas.

Cada subcarpeta es autocontenida (su propio `.gitignore`, dependencias y
tests).
