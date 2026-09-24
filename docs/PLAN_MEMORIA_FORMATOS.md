# Plan: memoria de formatos compartida (mediciones, plantilla, recetas)

Fecha: 2026-09-23. Extiende `PLAN_ASISTENTE_IA.md` (sección 12).

## 1. Objetivo

Que el usuario explique **una sola vez** cómo se procesa un tipo de archivo.
La próxima vez que alguien suba un archivo del mismo tipo, el sistema lo
reconoce, aplica la regla guardada y muestra la vista previa sin pedir nada.
Si no lo reconoce, el chat pide la explicación y, al confirmar, la guarda.

No es aprendizaje del modelo (no hay re-entrenamiento): es una memoria de
reglas, visible y editable. Se mantiene el contrato del asistente: la IA arma
la orden de trabajo, los motores deterministas escriben el archivo.

## 2. Decisiones tomadas

| Tema | Decisión |
|---|---|
| Alcance de la memoria | **Compartida** por todos los usuarios. |
| Formato reconocido | Se aplica la regla y se **muestra la vista previa**; el usuario genera con un clic. |
| Cuándo se guarda | **Solo si el usuario confirma** la vista previa ("¿Lo guardo como …?"). |
| Pantallas | Mediciones, Plantilla y Recetas por área, con un núcleo común. |

## 3. Conceptos

- **Huella**: resumen estructural de los archivos de la pantalla, calculado
  sin IA. Sirve para buscar en la memoria. No incluye datos (valores de
  mediciones, filas del listado), solo forma.
- **Regla**: el programa DSL que se ejecutó y el usuario confirmó, traducido
  a una forma **anclada** que sirva para otro archivo del mismo tipo (nunca
  números de fila ni de línea sueltos).
- **Formato**: `{id, pantalla, nombre, huella, regla, explicación original,
  creado_por, creado, usos, último_uso}`.

### 3.1 Qué se guarda y qué no

Se guarda solo lo **estructural** (cómo es el archivo). Lo que es un pedido
de esa corrida no se guarda: `filtrar_filas`, `solo_sufijos` y cualquier
otra operación que dependa de qué quiere generar el usuario hoy.

## 4. Flujo común

1. El usuario sube los archivos de la pantalla → se calcula la huella.
2. Búsqueda en la memoria de esa pantalla:
   - **Coincidencia única** (similitud ≥ umbral): se aplica la regla, se
     muestra la vista previa con "Reconocido como *nombre*" y un enlace
     "No es este formato".
   - **Varias candidatas cercanas**: el chat ofrece elegir.
   - **Ninguna**: el chat dice "No conozco este formato, ¿cómo se divide /
     cómo se llena?". Se ve igual la detección automática como punto de
     partida.
3. El usuario explica o corrige → plan → vista previa (flujo actual).
4. Al generar, si la regla aplicada no vino intacta de la memoria, el chat
   pregunta "¿Lo guardo como …?" con un nombre propuesto (editable).
   Confirmar crea el formato, o **actualiza** el reconocido si el usuario lo
   corrigió.
5. Si una regla guardada falla al aplicarse (ancla que no existe, columna
   ausente), no se adivina: se avisa y se vuelve al paso "Ninguna".

## 5. Por pantalla

### 5.1 Mediciones

**Prerrequisito (fase 0)**: interpretación confiable de la explicación.
- Rangos leídos de forma determinista del texto ("filas 1 a 41", "de la 43
  a la 53", "la fila 56 y 57"); la gramática obliga al modelo a devolver
  exactamente esos rangos, en ese orden.
- `con_encabezado: bool` pasa a `tipo: "listado" | "tabla"`; el modelo solo
  clasifica cada rango, viendo el fragmento de la frase que lo describe y
  sus 2 primeras líneas reales. Respaldo determinista: un rango de 2
  columnas con forma clave,valor que el usuario no describió como tabla
  queda como `listado`, aunque el modelo no responda.
- Chequeo plan vs. pedido: rangos o números mencionados que no se usaron se
  avisan en la pantalla.
- Front: selector Listado/Tabla en lugar del checkbox.

**Huella**: separador + secuencia de títulos de sección (`[Auftragsdaten]`,
`[Messprogrammseite 1]`, `# QSStat`) + forma de cada bloque (listado de 2
columnas / tabla de N columnas + primeros nombres de columna).

**Regla anclada**: cada tabla se expresa relativa a un ancla, ej.
`{ancla: "[Messprogrammseite 1]", hasta: "línea vacía", tipo: "tabla"}` o
`{ancla: "inicio de archivo", hasta: "[Messprogrammseite 1]", tipo: "listado"}`.
Al guardar, los números de fila de la explicación se traducen a anclas
(título o línea vacía más cercana). Evidencia de que hace falta:
`…280826_005.csv` (56 filas) y `…021224_000.csv` (59) comparten títulos en
las mismas filas, pero `…280826_006.csv` (211 filas) empieza directamente en
`[Messprogrammseite 1]`: son dos formatos distintos.

### 5.2 Plantilla

**Huella**: conjunto de campos `{...}` de la plantilla (con el prefijo de su
línea, ej. `#Codigo;`) + encabezados del listado.

**Regla anclada**: `asignar_columna` por **campo** (prefijo + nombre del
campo), no por número de línea; `nombre_archivo_desde` por nombre de
columna. Al aplicar, cada campo o columna que no exista invalida la regla.

### 5.3 Recetas por área

**Huella**: encabezados del listado (normalizados) + áreas presentes.

**Regla anclada**: `reemplazar_campo`, `nombrar_archivo`,
`agrupar_salida_por`, `quitar_comentarios`, todos por nombre de columna.
`filtrar_filas` y `solo_sufijos` no se guardan (§3.1).

## 6. Similitud

Por pantalla, una función determinista `similitud(huella_a, huella_b) → 0..1`:
Jaccard sobre títulos/campos/encabezados, con el separador y la forma de
bloques como condición necesaria en mediciones. Umbral inicial 0,8; se
ajusta con los archivos de `docs/`. Primero coincidencia exacta; la
similitud cubre variantes (un encabezado de más, un título renombrado).

## 7. Backend

- `app/ai/memoria/` : `huellas.py` (una función por pantalla),
  `anclaje.py` (programa → regla anclada, y regla + archivos → programa),
  `almacen.py` (persistencia).
- Persistencia: SQLite en la carpeta de datos del backend (compartida por
  todos; escrituras con transacción). Una tabla `formatos`; la huella y la
  regla como JSON.
- Endpoints: `POST /asistente/reconocer` (archivos → formato o nada),
  `POST /asistente/formatos` (guardar/actualizar), `GET/PATCH/DELETE
  /asistente/formatos[/{id}]` (administración).
- `asistente_service`: al subir archivos, primero `reconocer`; el plan del
  modelo solo interviene si no hay formato o el usuario pide cambios.

## 8. Front

- `AsistentePanel`: estado "Reconocido como …" / "Formato nuevo, explicámelo";
  diálogo de guardado con nombre editable tras generar.
- Pantalla **Formatos guardados**: lista por pantalla (nombre, usos, último
  uso, creado por), ver explicación original, renombrar, borrar.

## 9. Fases

| Fase | Contenido |
|---|---|
| 0 | ✅ Mediciones: rangos deterministas, `tipo` listado/tabla, chequeo plan vs. pedido, selector en el front. |
| 1 | ✅ Núcleo de memoria (almacén, endpoints, flujo reconocer/guardar en el panel) + mediciones. |
| 2 | ✅ Plantilla. |
| 3 | ✅ Recetas por área. |
| 4 | ✅ Pantalla de administración de formatos. |

Cada fase se cierra probando con los archivos reales de `docs/` (H1312 005,
006 y 021224_*, `plantilla.zip`, `Recetas/`).

## 10. Tests

- Huellas: dos archivos del mismo tipo dan la misma huella; 005 vs. 006 no.
- Anclaje: explicación con filas sobre 005 → regla anclada → aplicada a
  021224_000 produce las mismas tablas.
- Regla con ancla ausente → error explícito, no resultado parcial.
- Almacén: guardar, actualizar, reconocer, borrar; concurrencia básica.
- Recetas/plantilla: `filtrar_filas` nunca termina en la regla guardada.

## 11. Riesgos

- **Reconocimiento falso** (dos formatos parecidos): mitigado por la vista
  previa obligatoria y el enlace "No es este formato".
- **Memoria compartida pisada por error**: cada actualización guarda la
  versión anterior; la pantalla de administración permite volver atrás.
- **Anclaje ambiguo** (sin títulos ni líneas vacías cerca de un rango): se
  guarda por número de fila y se marca el formato como "frágil" en la lista.

## 12. Fuera de alcance

- Re-entrenar o ajustar el modelo.
- Guardar datos de los archivos (solo forma).
- Permisos por usuario sobre la memoria (se revisa si hace falta).
