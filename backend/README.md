# backend

Backend del nuevo sistema web (FastAPI, empaquetado con pywebview) que
unifica `máquina232` (Configurador de Planta) y `Diagramadora` (Conversor
de Mediciones). Reutiliza los 17 módulos de `máquina232/src/` copiándolos
a `backend/app/core/` (ver el plan). Implementación aún no iniciada — ver
[`PLAN_WEBAPP.md`](../PLAN_WEBAPP.md) en la raíz para la arquitectura
completa. `máquina232/` y `Diagramadora/` (las apps de escritorio
existentes) no dependen de esta carpeta y siguen usándose tal cual
mientras se construye esto.
