# Plan: editor de recetas tipo matriz (migración de `recipe_editor.py`)

> Estado: PLANIFICADO, sin implementar. Surge de la conversación de diseño del
> 2026-09-22, en el contexto de la fase 6 de `PLAN_ASISTENTE_IA.md` (limpieza
> de `máquina232/`/`Diagramadora/`): al auditar qué falta migrar antes de
> borrar esos directorios, apareció esta herramienta sin equivalente web.

## 1. Objetivo

`Diagramadora/recipe_editor.py` + `Diagramadora/ai/csv_recipe.py` (781 líneas)
son una app de escritorio separada, **de uso regular en planta**, para poner
a punto archivos CSV tipo "matriz de receta" (una fila por parámetro, una
columna por producto — formato `List separator=,` típico de HMI). El flujo:

1. Subir el `.csv` original → se genera un Excel formateado (producto por
   fila, parámetro por columna — más cómodo para editar que la matriz cruda).
2. Editar los valores que hagan falta en Excel, guardar.
3. Subir ese Excel + el `.csv` original de nuevo → se reconstruye el `.csv`,
   cambiando **únicamente** las celdas que efectivamente cambiaron. Todo lo
   demás (encabezados, filas de metadatos, fin de línea) queda byte a byte
   igual al original.
4. El motor se autoverifica: relee el archivo que acaba de escribir y
   confirma que cada cambio pedido quedó reflejado y que no se movió nada
   más. Si algo no cierra, marca `ALERTA`.

Este plan migra esa herramienta a una pantalla web nueva, sin tocar nada de
lo que ya existe.

## 2. Decisiones tomadas

| # | Decisión | Por qué |
|---|---|---|
| 1 | Pantalla nueva, estilo wizard simple (sin IA/chat) | El motor ya es 100% determinista — nunca inventa un valor, solo mueve lo que el usuario editó en Excel. No necesita el DSL ni el asistente; encaja con el patrón de `RecetasPorArea.tsx`/`GenerarRecetas.tsx`. |
| 2 | Si la autoverificación da `ALERTA`, se **bloquea la descarga** | Es un nivel de certeza distinto a las advertencias heurísticas de `PLAN_ASISTENTE_IA.md` sección 5: acá el propio motor está diciendo "lo que acabo de escribir no es lo que pedí". No tiene sentido ofrecer un archivo que el propio motor no puede confirmar. |
| 3 | Log de trazabilidad, mismo patrón que `app/ai/dsl/log.py` | Esta herramienta cambia parámetros de máquinas de producción más directamente que el asistente. Barato de agregar ahora que el patrón (`.jsonl` liviano en `datos/log/`) ya existe. |
| 4 | El servidor es *stateless* entre los dos pasos: el segundo paso pide de nuevo el `.csv` original | La app de escritorio recuerda la ruta del archivo entre pestañas; un backend HTTP no tiene ese estado. Coincide con cómo ya funciona `ImportarDialog`/`WizardMaquinaDialog` (piden de nuevo lo que hace falta). |
| 5 | Excel de salida: se porta `write_excel_recipe` tal cual (mismo estilo, misma hoja de instrucciones) | Ya está hecho y probado; `openpyxl` ya es dependencia del backend (`excel_import.py`). No hay razón para rehacerlo más simple. |

## 3. Diseño de la pantalla

Nueva ruta `/editor-recetas-matriz`, card nueva en
[Herramientas.tsx](front/src/pages/Herramientas.tsx), mismo patrón visual
que las otras 3.

**Paso 1 — Exportar a Excel**
- Subir el `.csv`/`.txt` original.
- `POST /api/editor-recetas/exportar` → devuelve el `.xlsx` para descargar
  (`Content-Disposition: attachment`), con nombre `<original> (editable).xlsx`.
- Mensaje: cantidad de productos × parámetros detectados, y el recordatorio
  de que el paso 2 necesita el Excel editado **+ el mismo `.csv` original**.

**Paso 2 — Aplicar cambios**
- Subir el `.csv` original (de nuevo) + el `.xlsx` ya editado.
- `POST /api/editor-recetas/aplicar` → devuelve un reporte JSON: cantidad de
  celdas cambiadas, lista de cambios (parámetro, producto, valor anterior,
  valor nuevo), advertencias, y si hubo `ALERTA` (bloquea el botón de
  descarga).
- Si no hay `ALERTA`: botón "Descargar `.csv` actualizado" →
  `POST /api/editor-recetas/aplicar/descargar` con los mismos archivos
  (evita mantener estado de sesión en el servidor; el costo de re-procesar
  es insignificante para un archivo de este tamaño).

No hace falta un componente nuevo de diseño: reutiliza `.card`, `.toolbar`,
`.error`, `.badge` ya existentes. Un único componente nuevo,
`components/ListaCambios.tsx`, para la tabla de cambios (reusable si en el
futuro otra pantalla necesita mostrar un diff).

## 4. Backend

```
backend/app/ai/csv_recipe.py          # migrado de Diagramadora/ai/, con tests
backend/app/services/editor_recetas_service.py
backend/app/routers/editor_recetas.py
```

- `csv_recipe.py` se migra **tal cual** (es un módulo puro, sin Tkinter ni
  I/O de sesión — mismo criterio que `plantillas_masivas.py`). Único cambio:
  `write_excel_recipe`/`rebuild_csv` reciben rutas de archivo hoy; el
  servicio web los envuelve con archivos temporales (mismo patrón que
  `mediciones_service.procesar`, que ya usa `tempfile.mkdtemp`).
- `rebuild_csv(...).ok` (ya existe: `False` si hay algún warning que
  empieza con `"ALERTA"`) es exactamente el criterio de bloqueo de la
  decisión 2 — no hace falta agregar nada nuevo al motor.
- Log de trazabilidad: `backend/app/core/log_jsonl.py` (nuevo, genérico:
  `registrar(origen, campos)`/`leer_eventos(origen)`, un `.jsonl` por
  origen dentro de `datos/log/`). `app/ai/dsl/log.py` del asistente queda
  intacto (no se tocó código ya probado solo para reusar); el editor de
  recetas es el segundo consumidor de este patrón, ya generalizado.
  Registra timestamp, usuario, archivo, cantidad de cambios — **no** el
  detalle de cada celda (eso ya lo tiene el reporte que se le muestra al
  usuario) — y **solo si `aplicar_y_descargar` tuvo éxito** (una `ALERTA`
  rechazada no deja rastro, porque no se aplicó nada).

## 5. Tests

- `csv_recipe.py`: portar/adaptar los casos que ya cubrían esto en
  `Diagramadora` (si existían) + casos nuevos: round-trip byte-exacto sin
  ediciones, una edición simple, un código de producto que no matchea
  (warning, no aplica el cambio), un `ALERTA` forzado (ej. mockeando una
  discrepancia post-escritura) para probar el bloqueo end-to-end.
- Service/router: exportar → aplicar sin `ALERTA` → descarga disponible;
  aplicar con `ALERTA` → descarga bloqueada (400 o campo `bloqueado: true`).
- Verificación en navegador real (mismo criterio que las fases anteriores):
  subir un `.csv` de prueba, bajar el Excel, editarlo (vía `openpyxl` en un
  script, no a mano), subirlo, confirmar el `.csv` resultante.

## 6. Fases

| Fase | Qué | Listo cuando |
|---|---|---|
| A | ✅ Migrar `csv_recipe.py` + tests | 15 tests: round-trip byte-exacto, edición simple, código desconocido, valor vacío/no-numérico, `ALERTA` real (valor con salto de línea embebido), round-trip completo vía Excel |
| B | ✅ Servicio + endpoints `/api/editor-recetas/*` + log | Verificado por HTTP real: exportar → Excel válido; aplicar sin `ALERTA` → preview + descarga con solo la celda tocada distinta; aplicar con `ALERTA` → `bloqueado: true` en preview y `400` en `/aplicar/descargar` (el bloqueo es del servidor, no solo de la UI) |
| C | ✅ Front: pantalla nueva + card en Herramientas | Verificado en el navegador real: exportar (descarga xlsx), editar una celda, subir ambos archivos, "1 cambio(s) detectado(s)" con la tabla correcta, descarga `200 OK`. Sin errores de consola. |
| D | ✅ Borrado de `máquina232/` y `Diagramadora/` | Sin referencias funcionales (verificado: nada en `build.bat`, specs de PyInstaller, imports). Datos reales sin versionar (`datos_reales_privados/`, `datos/`, `datos232/`, `respaldos_previos/`, `_backup_pre_universal/`) movidos fuera del repo antes de borrar — nunca estuvieron en git, no eran recuperables. 175 archivos versionados borrados con `git rm` (staged, sin commitear). Suite verde (416 tests) y TypeScript limpio después del borrado. |

## 7. Riesgos

- El tamaño real de los `.csv` en planta no está confirmado — si son muy
  anchos (muchos productos), el Excel transpuesto podría tener muchas
  columnas. `write_excel_recipe` ya lo maneja (una columna por parámetro),
  pero vale confirmar con un archivo real antes de dar la fase por cerrada.
- Nombres de archivo con espacios/acentos en el `Content-Disposition` —
  mismo cuidado que ya se tomó en `asistente.py` (header ASCII-safe).

## 8. Fuera de alcance

- Editar la matriz directamente en el navegador (sin pasar por Excel): el
  flujo actual ya funciona y el personal de planta ya lo conoce.
- Unificar este formato con el de `recetas_por_area.py`/`plantillas_masivas.py`
  — son dos formatos de archivo genuinamente distintos.
