# Plan: importación desde Excel con clave de búsqueda y mapeo de datos separados

> Estado: **planificación, sin implementar**.
> Complementa a `PLAN_PARIDAD_UI.md` (sección 7.5, `ImportarDialog`), que describe
> el flujo actual y queda superado en lo que se indica acá.

**Decisiones tomadas con el usuario (2026-10-09)**

| Tema | Decisión |
|---|---|
| Clave de búsqueda | Una sola columna. Es el código que la máquina toma como PK para ponerse a punto: **número o sellado, uno u otro**, nunca los dos a la vez |
| Código repetido | Se marca como **conflicto** y no se importa, ni en el sistema ni en el Excel, hasta corregir el dato |
| Celda vacía en el Excel | **No toca** el dato actual del sistema |
| Código del Excel que no existe en el sistema | **Solo aviso**. No se crea ningún registro y no se modifica nada. El ingeniero lo carga |
| Campo de búsqueda | **Nunca** se actualiza desde el Excel |
| Excel | Es de solo lectura. El flujo **nunca** modifica el archivo; el Excel es la fuente que modifica el sistema |

**Pendientes de confirmar** (ver sección 10): bajas y si el ID se ofrece como clave de búsqueda.

---

## 1. Diagnóstico: por qué el flujo actual no sirve con ID automático

- El cruce usa la **PK** en todo el motor: `DataStore.find_key` ([datastore.py:507](backend/app/core/datastore.py:507)) indexa por `campo_clave()`, y `key_of`, `is_placeholder` y la detección de duplicados dependen de esa misma clave.
- Con ID automático, la PK es el ID (`sintetica`, [profile.py:112](backend/app/core/profile.py:112)). El ID **no viene en el Excel** de la máquina. Por eso el paso de mapeo obliga a elegir "una columna del Excel como ID" ([import_service.py:136](backend/app/services/import_service.py:136)), algo que el usuario no puede hacer bien.
- En un perfil de ID automático, el código de la máquina queda como campo `parametro` ([profile_builder.py:349](backend/app/core/profile_builder.py:349)). Hoy aparecería como dato a sobrescribir, lo que contradice la decisión de que el campo de búsqueda nunca se actualiza.
- Las altas hoy crean registros con ID nuevo ([datastore.py:464](backend/app/core/datastore.py:464)). Esto deja de existir en este flujo.

**Conclusión:** el cambio es de motor de datos y de servicio, no solo de pantalla. Hay que separar "por qué campo busco" de "cuál es la PK".

---

## 2. Modelo del mapeo (dos secciones)

| Sección | Qué define | Cantidad | Obligatoria |
|---|---|---|---|
| **1. Clave de búsqueda** | Campo del sistema + columna del Excel que se cruzan | Exactamente una | Sí |
| **2. Datos a actualizar** | Columna del Excel → campo `parametro` del sistema | Una o más | Al menos una |

Reglas:

- **Campos elegibles en la sección 1:** todos los campos visibles del perfil **excepto el ID sintético**. Así sirve tanto para el código de número como para el de sellado sin tocar el perfil.
- **Campos elegibles en la sección 2:** solo `parametro` visibles. Nunca el campo de búsqueda, nunca el ID.
- **Una columna del Excel, un solo campo** entre las dos secciones. Se valida en backend y se deshabilitan en la UI las opciones ya usadas.
- La elección es **por importación**. El perfil de la máquina no cambia.

---

## 3. Datastore: búsqueda por campo, sin tocar la PK

- Nuevo método `DataStore.indice_por_campo(campo) -> dict[str, list[int]]`: agrupa los índices de los registros por el valor normalizado del campo.
- `find_key` y `_indice_claves` **no cambian**: siguen siendo la PK y los usa el resto del sistema.
- **Normalización compartida** (una sola función, usada por el Excel y por el sistema):
  - Campo `texto`: `strip()`, sin distinguir ceros a la izquierda.
  - Campo numérico (`entero`, `entero_ceros`): comparación por **valor**, así `"0012"` del Excel coincide con `12` del sistema. Se confirma en los tests.
  - Campo `decimal`: valor normalizado con el separador ya resuelto por `excel_import`.
- El índice se arma **una vez por importación** (en `mapear`). Con catálogos de hasta 10.000 registros el costo es despreciable.

---

## 4. Servicio de importación

### 4.1 `mapear(import_id, busqueda, mapeo)`

Validaciones (mensajes en español, como hoy):

1. Falta el campo o la columna de la clave de búsqueda → "Elegí qué columna del archivo corresponde a la clave de búsqueda."
2. El campo de búsqueda aparece en la sección 2, o es el ID → rechazar.
3. Ningún dato a actualizar → "Mapeá al menos un dato a actualizar."
4. Una columna usada en dos lugares (entre secciones o dentro de la 2) → rechazar.
5. Una columna que no existe en la hoja elegida → rechazar.

Cálculo, fila por fila del Excel:

| Caso | Resultado |
|---|---|
| Clave del Excel vacía | Se ignora y se cuenta en `filas_sin_clave` |
| La clave aparece en **más de una fila** del Excel | `conflicto` (motivo: "aparece N veces en el archivo"). No se importa ninguna de esas filas |
| La clave coincide con **más de un registro** del sistema | `conflicto` (motivo: "N registros del sistema tienen este código") |
| La clave no coincide con ningún registro | `sin_coincidencia`. Solo aviso |
| Coincidencia única | Se comparan los campos de la sección 2. Si la celda del Excel está vacía, no cuenta como cambio. Si cambia, va a `diffs` con la validación de rango de hoy |

Registros del sistema que no aparecen en el Excel (no placeholders) van a `obsoletos` (ver pendiente P1).

Placeholders: hoy se detectan por la PK. Con la clave de búsqueda, se evalúa el **valor de búsqueda** con el patrón del perfil ([profile.py:144](backend/app/core/profile.py:144)).

Identificación en la respuesta:

- Cada diff y cada obsoleto lleva `id` = **PK del registro** (siempre única) y `busqueda` = valor de la clave de búsqueda, que es lo que el usuario reconoce. Así la selección funciona igual con ID automático.
- `conflictos` y `sin_coincidencia` llevan `codigo` = valor del Excel (no hay registro).

Respuesta:

```
{ diffs, conflictos, sin_coincidencia, obsoletos, sin_cambios, filas_sin_clave }
```

### 4.2 `aplicar(import_id, diffs_sel, obsoletos_sel, hash_esperado)`

- Se elimina `nuevos_sel` y toda llamada a `store.add` / `nuevo_registro` de este flujo: **no hay altas**.
- Cada selección se **vuelve a resolver** contra el store fresco por PK (`find_key`, no por índices guardados). Si el registro ya no es único por clave de búsqueda, se omite y se informa en `omitidos`.
- `store.update` solo recibe los campos de la sección 2 con valor no vacío. Nunca el campo de búsqueda ni el ID.
- Un solo backup y un evento de historial por registro (sin cambios respecto de hoy).
- Respuesta: `{ hash, modificados, eliminados, omitidos }`.

---

## 5. Memoria del mapeo (`import_mapeos`)

- Formato nuevo, en el mismo `import_mapeo.json` de la máquina:
  ```json
  { "busqueda": { "campo": "codigo_numero", "columna": "Código" },
    "mapeo":    { "color": "Color", "grams": "Gramos" } }
  ```
- Lectura de formato viejo (plano, sin `busqueda`): se interpreta como `mapeo`; la clave cae al default.
- Archivo corrupto o con forma inesperada → vacío, como hoy ([import_mapeos.py:19](backend/app/core/import_mapeos.py:19)).
- `aplicar_a_headers` se aplica a ambas secciones.

---

## 6. API

| Endpoint | Cambio |
|---|---|
| `POST /api/maquinas/{id}/import/mapping` | Body: `{ import_id, busqueda: {campo, columna}, mapeo: {campo: columna} }` (antes solo `mapeo`). Respuesta según 4.1 |
| `POST /api/maquinas/{id}/import/apply` | Body: `{ import_id, diffs: [id], obsoletos: [id], hash_esperado }` (sin `nuevos`) |
| `POST /api/maquinas/{id}/import/start` y `/hoja` | Sin cambios de contrato. La sugerencia incluye un default para la clave de búsqueda |

El único consumidor es el frontend, así que el cambio de contrato es seguro. Tipos en [api.ts:791](front/src/api.ts:791) (`ImportDiffRegistro`, `ImportMapeoResultado`) y en el mismo bloque.

**Default de la clave de búsqueda** (sugerencia): la última usada si está en la memoria; si no, la PK cuando no es sintética; si no, vacía (obligatorio elegir).

---

## 7. Frontend: `ImportarDialog`

### 7.1 Paso "Mapear columnas", en dos secciones

**1. Clave de búsqueda** (obligatoria)
- Texto: "Código que la máquina usa para identificar cada registro. Cada fila del Excel se busca por este valor."
- Dos selects: "Campo del sistema" (sin ID) y "Columna del Excel".

**2. Datos a actualizar**
- Texto: "Si la celda del Excel está vacía, el dato actual no se toca."
- Un select por campo `parametro` visible, con "— no importar —" por defecto. Excluye el campo de búsqueda.

La vista previa de las 3 primeras filas se mantiene.

### 7.2 Paso "Revisar cambios"

Resumen: `N con diferencias · M sin cambios · K sin coincidencia · C con conflicto · F filas sin clave`.

| Bloque | Interacción |
|---|---|
| **Modificaciones** | Checkbox, con "Todos" y "Ninguno". No marca los que tienen error de rango (como hoy) |
| **Conflictos** (no se importan) | Lista en rojo con el motivo. Sin checkbox |
| **Sin coincidencia en el sistema** | Aviso informativo con los códigos: "No se crean ni se modifican. El ingeniero los carga." Sin checkbox |
| **Obsoletos** | Según pendiente P1 |

El diálogo de confirmación de "Aplicar" ya no menciona altas.

---

## 8. Pasos de implementación

1. **Datastore**: `indice_por_campo` y la normalización compartida. Tests unitarios.
2. **`importacion.calcular_diferencias`**: nueva firma (campo de búsqueda + mapeo), conflictos, sin coincidencia y filas sin clave. Tests unitarios.
3. **`import_mapeos`**: formato nuevo con lectura del viejo. Tests.
4. **`import_service`**: `mapear` y `aplicar` con las validaciones y la respuesta de la sección 4. Tests de API.
5. **Router y `api.ts`**: body nuevo y tipos.
6. **`ImportarDialog.tsx`**: paso de mapeo en dos secciones y paso de revisión con conflictos y sin coincidencia.
7. **Verificación** (sección 9).
8. **Docs**: actualizar la sección 7.5 de `PLAN_PARIDAD_UI.md` y agregar este plan a `README.md`. Al final, `graphify update .` (ver `CLAUDE.md` del proyecto).

---

## 9. Verificación

**Tests del backend** (`backend/`, con `backend/.venv/Scripts/python.exe -m pytest -q`):

Adaptar los existentes:
- `test_api_importacion.py`: "exige la columna clave" → "exige la clave de búsqueda"; los casos de `nuevos` pasan a `sin_coincidencia`; `aplicar` ya no recibe `nuevos`.
- `test_importacion.py`: reescribir los casos de `calcular_diferencias` con búsqueda por un campo distinto de la PK.
- `test_import_mapeos.py`: formato nuevo y lectura del formato viejo.

Casos nuevos:
1. Búsqueda por un campo que no es la PK (perfil con ID automático) encuentra y modifica el registro correcto.
2. Clave repetida en el Excel → conflicto; ninguna de esas filas se aplica.
3. Clave repetida en el sistema → conflicto.
4. Código del Excel sin coincidencia → `sin_coincidencia`, y `aplicar` no crea ni un registro.
5. Celda vacía en el Excel no pisa el dato.
6. El campo de búsqueda no cambia, aunque el Excel traiga otro valor en esa columna.
7. Numérico: `"0012"` del Excel coincide con `12` del sistema.
8. El ID no aparece como opción en la sección 1 ni en la 2, y nunca se escribe.
9. Filas sin clave se ignoran y se cuentan.
10. Placeholders no cuentan como obsoletos (evaluados por el valor de búsqueda).
11. Si entre mapeo y aplicar un código deja de ser único, se omite y aparece en `omitidos`.

**Frontend**: `npx tsc --noEmit` y `npm run lint` (en `front/`), y `npm run build` sin errores.

**Prueba manual**: con un archivo real de la máquina y su perfil de ID automático. Hace falta que me pases un Excel de prueba.

---

## 10. Pendientes de confirmar

**P1. Bajas (códigos del sistema que no están en el Excel).** Hoy son opcionales (checkbox) y borran al aplicar.
- a) **Recomendado:** mantener el checkbox. Cada baja es opt-in, y la importación entera se puede deshacer de una vez ([PLAN_PARIDAD_UI.md](docs/PLAN_PARIDAD_UI.md), B3).
- b) Pasar a solo aviso, igual que las altas.

**P2. ID como clave de búsqueda.** Hoy no aparece en la sección 1.
- a) **Recomendado:** no ofrecerlo. El Excel de la máquina no trae ID.
- b) Ofrecerlo como opción, por si algún Excel exportado del sistema lo trae.

---

## 11. Riesgos

- **Cambio de contrato de API:** el único consumidor es el frontend, que se actualiza en el mismo cambio.
- **Un valor de búsqueda no es único por naturaleza:** se acepta, y se resuelve como conflicto (no como error silencioso).
- **Mapeo recordado en formato viejo:** la migración de lectura evita perderlo; los tests lo cubren.
- **Sin altas desde el Excel:** los códigos nuevos quedan visibles como aviso y el ingeniero los carga. Si la carga manual se atrasa, el aviso se repite en cada importación hasta que se carguen.
