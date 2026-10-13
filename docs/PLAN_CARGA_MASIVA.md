# Plan: carga masiva de registros nuevos desde Excel

> Estado: **implementado**. Tests: `backend/tests/test_carga_masiva.py`.
> Pendiente: prueba manual del diálogo con una máquina real.
> Complementa a `PLAN_IMPORTACION_CLAVE_BUSQUEDA.md`: la actualización masiva
> sigue igual; este plan agrega la carga masiva al mismo diálogo `ImportarDialog`.

**Decisiones tomadas con el usuario (2026-10-13)**

| Tema | Decisión |
|---|---|
| Modos | El diálogo arranca con dos botones: **Carga masiva** y **Actualización masiva**. El flujo se divide ahí |
| Actualización masiva | Queda como está hoy (no toca, no crea, no vacía celdas) |
| Carga masiva: altas | Solo altas. Cada fila del Excel que no existe en el sistema crea un registro nuevo con **ID automático** |
| Carga masiva: claves | Hasta **dos** campos como clave (p. ej. amortiguador y número de sellado). Cada clave se mapea a una columna del Excel |
| Código ya cargado | Si las claves de la fila coinciden con un registro existente, ese registro **se modifica** con los datos del archivo (no se crea otro) |
| Celda vacía (carga) | Campo numérico → `0`. Campo de texto → `Null` |
| Fila sin valor en alguna clave | Se cuenta como "fila sin clave" y no se importa |
| Claves repetidas en el Excel o en el sistema | **Conflicto**: no se importa esa clave hasta corregir el dato |
| Errores de rango (min/max) | Bloquean esa fila, igual que en la actualización |

## Decisiones propias (no pedidas)

- **Clave compuesta**: la búsqueda pasa de un solo campo a 1 o 2 campos. Se usa
  `clave_busqueda` por campo y se unen con `" · "`. Una fila con alguna clave vacía no se indexa.
- **Perfil sin ID automático**: la PK (`campo_clave`) tiene que ser una de las
  claves, porque es el código que identifica el registro. Además, un alta no puede
  repetir una PK ya existente en el sistema (se marca como conflicto).
- **Vacío en carga se aplica también a registros existentes que se modifican**:
  es lo que pidió el usuario ("vacío = 0/Null" en la carga). Un Excel con celdas
  vacías en un registro existente sí borra ese dato. Queda señalado para revisar.
- **Valores no interpretables en campos numéricos** (p. ej. "N/C") se tratan como
  vacíos y quedan en 0. Mismo criterio que el vacío. Queda señalado.
- **Sin memoria de mapeo**: la carga masiva no guarda el mapeo en `import_mapeos`
  (esa memoria es de la actualización y tiene una sola clave).

## Piezas que cambian

- `backend/app/core/importacion.py`: `indice_por_claves` (clave compuesta).
- `backend/app/services/import_service.py`: `mapear_carga` y `_aplicar_carga`;
  `aplicar` despacha según el modo de la sesión.
- `backend/app/routers/importacion.py`: endpoint `/import/mapping-carga` y
  campo `altas` en `/import/apply`.
- `front/src/api.ts`: `importMapearCarga`, `importAplicar(..., altas)` y tipos.
- `front/src/dialogs/ImportarDialog.tsx`: fase de modo, claves compuestas en el
  mapeo y sección de altas en la revisión.
