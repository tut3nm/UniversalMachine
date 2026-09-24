# Universal Machine

Sistema web (FastAPI + React) para configurar parámetros de máquinas de
planta: `front/` es el cliente, `backend/` el servidor. Reemplaza dos apps
de escritorio (`máquina232`, Configurador de Parámetros de Planta; y
`Diagramadora`, conversor de mediciones + editor de recetas), ya migradas
y borradas del repo — `git log` conserva su historia si hace falta.

Planes de diseño e implementación, en la raíz:

- [`PLAN_WEBAPP.md`](PLAN_WEBAPP.md) — arquitectura general del sistema web.
- [`PLAN_PARIDAD_UI.md`](PLAN_PARIDAD_UI.md) — migración de la interfaz de
  máquina232 (tabla, diálogos, atajos).
- [`PLAN_GENERADOR_RECETAS.md`](PLAN_GENERADOR_RECETAS.md) — generador de
  archivos desde plantilla y desde catálogo por área.
- [`PLAN_ASISTENTE_IA.md`](PLAN_ASISTENTE_IA.md) — asistente embebido con
  IA local (DSL de operaciones, `llama-server`).
- [`PLAN_EDITOR_RECETAS_MATRIZ.md`](PLAN_EDITOR_RECETAS_MATRIZ.md) —
  editor de recetas tipo matriz vía Excel.
- [`PLAN_MEMORIA_FORMATOS.md`](PLAN_MEMORIA_FORMATOS.md) — memoria
  compartida de formatos: explicar un tipo de archivo una vez y reconocerlo
  solo después.

Cada subcarpeta (`front/`, `backend/`) es autocontenida (su propio
`.gitignore`, dependencias y tests).
