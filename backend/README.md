# backend

Backend del sistema web (FastAPI, empaquetado con pywebview) que reemplaza
las apps de escritorio `máquina232` (Configurador de Planta) y
`Diagramadora` (Conversor de Mediciones): ambas quedaron migradas y sus
directorios se borraron del repo (`git log` conserva la historia si hace
falta consultarlas).

`app/core/` son los módulos del motor original (perfil, datastore,
historial, backups, etc.), reutilizados prácticamente sin cambios.
`app/ai/` son los motores de generación/validación de archivos (recetas por
área, plantillas masivas, editor de recetas matriz, tabulación de
mediciones, el DSL del asistente). `app/routers/` + `app/services/`
exponen todo eso por HTTP; `front/` es el cliente React.

Ver los planes en la raíz del repo para el diseño de cada parte:
[`PLAN_WEBAPP.md`](../PLAN_WEBAPP.md) (arquitectura general),
[`PLAN_PARIDAD_UI.md`](../PLAN_PARIDAD_UI.md) (migración de la interfaz de
máquina232), [`PLAN_GENERADOR_RECETAS.md`](../PLAN_GENERADOR_RECETAS.md),
[`PLAN_ASISTENTE_IA.md`](../PLAN_ASISTENTE_IA.md) y
[`PLAN_EDITOR_RECETAS_MATRIZ.md`](../PLAN_EDITOR_RECETAS_MATRIZ.md).
