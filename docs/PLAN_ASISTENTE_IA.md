# Plan: asistente conversacional con IA local + DSL de operaciones

> Estado: fases 1-7 implementadas (la 7, sección 12, corrige las decisiones
> 4 y 7). Surge de la conversación de diseño del 2026-09-22.

## 1. Objetivo

Hoy cada herramienta es una pantalla con inputs fijos ([RecetasPorArea.tsx](front/src/pages/RecetasPorArea.tsx),
[GenerarRecetas.tsx](front/src/pages/GenerarRecetas.tsx), [Mediciones.tsx](front/src/pages/Mediciones.tsx)).
El usuario tiene que saber de antemano qué herramienta necesita y cómo se
llaman las columnas que espera.

La idea es que pueda **escribir en lenguaje natural qué necesita** y que el
sistema arme la tarea, en un panel lateral presente en esas pantallas, con
tarjetas de prompt precargado arriba del campo de texto.

Dos cosas que este plan **no** hace, y son el núcleo de su diseño:

1. **La IA no escribe archivos.** Los archivos van a máquinas de producción.
   El modelo arma la orden de trabajo; los motores deterministas ya testeados
   siguen siendo los únicos que generan contenido.
2. **La IA no escribe prosa.** Todas las burbujas del asistente las redacta
   nuestro código a partir de una estructura. Con un modelo de 1.5B, esa es
   la diferencia entre una herramienta seria y uno que dice cualquier cosa.

## 2. Decisiones tomadas

| # | Decisión | Por qué |
|---|---|---|
| 1 | Se mantiene el modelo local actual: **Qwen2.5-1.5B-Instruct Q4_K_M** | Ya está, es offline, y con el diseño de la sección 3 alcanza. Nada sale de la empresa. |
| 2 | Se pasa de `subprocess` por llamada a **`llama-server` persistente** | Hoy cada llamada recarga 1,1 GB de disco. En un chat eso es inviable. El `.exe` ya está en `backend/runtime/llama/`. |
| 3 | La IA emite un **programa en un DSL de operaciones**, no contenido | Los valores salen siempre de los archivos de entrada; el modelo elige *qué operación*, nunca *qué valor*. Un `TEP` alucinado deja de ser posible por construcción. |
| 4 | Alcance v1 del DSL: **3 operaciones gruesas + las finas del mundo recetas** | Las gruesas son el espejo de las pantallas de hoy; las finas son las que habilitan pedidos no previstos. La tabulación entra solo como operación gruesa. |
| 5 | **Gramática GBNF en dos etapas** (intención → parámetros) | La gramática de parámetros se genera con los encabezados reales del archivo subido, así el modelo no puede inventar un nombre de columna. |
| 6 | **Sin Tailwind ni shadcn**: HoverCard y burbujas a mano | El front es CSS propio ([base.css](front/src/styles/base.css), [ui.css](front/src/styles/ui.css)) + [ui.tsx](front/src/ui.tsx). shadcn exige Tailwind + Radix; no vale arrastrar eso por dos componentes. |
| 7 | El panel vive **solo en las 3 pantallas de herramientas** | Las pantallas heredadas de máquina232 (detalle, backups, historial, duplicados, importación) quedan exactamente como están: sin panel, sin cards, sin IA. |
| 8 | **Validación de consistencia** antes de descargar + auditoría de carpetas existentes | Ver sección 5: hay dos recetas rotas hoy en `docs/Recetas/`. |
| 9 | Trazabilidad: **log liviano + el programa DSL ejecutado** | El programa son 5 líneas estructuradas; guardarlo cuesta lo mismo que el log liviano y permite reconstruir el origen de una receta mal cargada. |
| 10 | Se borran `máquina232/` y `Diagramadora/` **al final**, después de migrar lo que falta | Ver sección 7. La interfaz de edición de registros CSV dentro de la webapp no se toca. |

## 3. Arquitectura: el DSL como lengua franca

### 3.1 Vocabulario de operaciones

Ninguna operación se inventa: cada una sale de algo que el código ya hace.

**Gruesas** (envuelven un motor existente, equivalen a las pantallas de hoy):

| Operación | Motor que envuelve |
|---|---|
| `generar_recetas_por_area` | [recetas_por_area.py](backend/app/ai/recetas_por_area.py) |
| `generar_desde_plantilla` | [plantillas_masivas.py](backend/app/ai/plantillas_masivas.py) |
| `tabular_mediciones` | `structure.py` + `labeler.py` + `generic_excel.py` |

**Finas** (los pasos internos, ahora componibles):

| Operación | Qué hace |
|---|---|
| `mapear_columna(encabezado -> rol)` | Resuelve que "Cod. Sellado" es la columna `sellado` |
| `reemplazar_campo(campo <- origen)` | `origen` = `columna:X` \| `literal:"..."` \| `plantilla` (dejar como está) |
| `filtrar_filas(columna, op, valor)` | Recorta el listado |
| `expandir_por_catalogo(area, solo_sufijos?)` | Una fila → N archivos, opcionalmente limitado a ciertos sufijos |
| `nombrar_archivo(patron)` | Patrón con slots: `"{sellado}.{sufijo}.def.txt"` |
| `agrupar_salida_por(columna)` | Carpetas dentro del `.zip` |
| `quitar_comentarios()` | Saca las notas `//` (hoy es comportamiento fijo) |

El fin de línea original (CRLF) se preserva siempre; no es una operación
negociable por el modelo.

**Regla de crecimiento del DSL**: no se agrega una operación sin un pedido
real que la haya requerido. El catálogo no crece "por si acaso".

### 3.2 Ejemplo que hoy es imposible sin tocar código

> *"De este listado, generá solo las recetas .15 y .17 de las filas HD, y
> nombralas con el amortiguador en vez del sellado"*

```
filtrar_filas(area == "HD")
expandir_por_catalogo(area, solo_sufijos=["15","17"])
reemplazar_campo(#Codigo      <- columna:sellado)
reemplazar_campo(#Descripcion <- columna:amortiguador)
nombrar_archivo("{amortiguador}.{sufijo}.def.txt")
```

### 3.3 Gramática en dos etapas

1. **Intención**: gramática = enum cerrado de operaciones gruesas + la
   alternativa `desconocido`. Un 1.5B acierta esto casi siempre.
2. **Parámetros**: gramática generada en el momento, que solo admite como
   literales **los encabezados que el archivo subido realmente tiene**, y los
   sufijos que el catálogo del área realmente tiene. Mismo principio que
   [build_labeling_grammar](backend/app/ai/llm.py:101), que ya fija las claves
   permitidas.

`desconocido` siempre está disponible en la raíz: el modelo puede decir "no
sé" y la tarjeta aparece con los slots vacíos resaltados para que los complete
el ingeniero. **Nunca adivina en silencio.**

### 3.4 Contrato de seguridad

Lo que el modelo **no puede** hacer, garantizado por construcción y no por
buena conducta:

- emitir un valor que termine dentro de un archivo (todos vienen de la entrada);
- nombrar una columna que no exista;
- elegir un sufijo de operación que el catálogo del área no tenga;
- generar texto que se le muestre al usuario sin pasar por nuestro renderizado.

### 3.5 Módulos nuevos

```
backend/app/ai/dsl/
    operaciones.py    # catalogo declarativo: nombre, params, tipos, motor
    gramatica.py      # genera GBNF desde el catalogo + el contexto
    interprete.py     # ejecuta el programa contra los motores
    planificador.py   # orquesta: contexto + texto -> programa (2 etapas)
```

El programa es JSON: `{"operaciones": [{"op": "...", "args": {...}}, ...]}`.
Antes de ejecutar se valida igual que se validan hoy los listados: que cada
arg referencie algo que existe, que haya exactamente una operación de nombre
de archivo, que no se pisen operaciones incompatibles.

## 4. Runtime de IA: de `subprocess` a `llama-server`

- Levantar `llama-server.exe -m <modelo> -c 8192 -t 4 --host 127.0.0.1
  --port <p>` como proceso hijo, en el `lifespan` de [main.py](backend/app/main.py:38)
  (donde ya se adquiere el lock de instancia), y bajarlo en el `finally`.
- `llm.py` gana `run_llm_server()` que hace `POST /completion` con
  `{prompt, grammar, temperature: 0, n_predict}`. Se **mantiene**
  `run_llm()` por subprocess como fallback: si el server no levanta, el
  labeler de mediciones tiene que seguir funcionando igual que hoy.
- `GET /api/asistente/estado` reporta si el server está vivo, con el mismo
  criterio que el `/api/mediciones/estado` existente.
- Cuidado explícito con procesos huérfanos si el backend muere mal.

## 5. Validación de consistencia

Motivación concreta: revisando un puñado de archivos aparecieron **dos
defectos reales que están hoy en el repo**.

- `RecetasHD/001789002323.17.def.txt` tiene `#Descripcion;47700019342`
  (11 dígitos), mientras que las variantes `.15` y `.19` del mismo sellado
  tienen `471700019342` (12). Falta un dígito.
- `RecetasGPS2/Obsoletos/004981008611.20.def.txt` tiene
  `#Codigo;001789010000`, que no coincide con su propio nombre de archivo.

**Las reglas deterministas son las que cazan esto**, no la IA:

| Regla | Qué detecta |
|---|---|
| Longitud/formato de código inconsistente entre variantes del mismo sellado | El primer caso |
| `#Codigo` que no coincide con el nombre del archivo | El segundo caso |
| `TEP` que no arranca con el número de operación del sufijo | Se cumple en todos los ejemplos revisados (15→15.xx, 13.5→13.50, 26→26.00) |
| Códigos repetidos en el listado, campos vacíos, no-numérico donde siempre hay número | Errores de carga |

La IA se suma **arriba** de las reglas, no en lugar de ellas: rankear qué
anomalía mirar primero, detectar el "este código se parece sospechosamente a
otro pero no es igual", y redactar el hallazgo. Sale más barato y agarra más.

Dónde vive:
- `backend/app/ai/validacion_recetas.py` (reglas puras, testeables).
- En el paso de **previsualización** que ya existe antes de bajar el `.zip`.
- `POST /api/recetas-por-area/auditar`: audita los catálogos del repo, para
  encontrar los archivos rotos que ya están dando vueltas. Botón "Auditar
  recetas existentes" en la pantalla.
- Reporta y advierte; **(TBD)** si además bloquea la descarga o solo avisa.

## 6. Front

Componentes nuevos, todos en el sistema de estilos actual:

- `components/HoverCard.tsx` — popover con delay, que responde a **hover,
  focus y tap** (la PC de planta puede ser táctil; el hover solo no alcanza).
- `components/PlanCard.tsx` — la burbuja del asistente: operación, parámetros
  editables, slots faltantes resaltados, botón Ejecutar. No es prosa.
- `components/AsistentePanel.tsx` — el panel lateral colapsable. Recibe por
  props el **contexto de la pantalla** (máquina actual, archivos cargados,
  encabezados detectados), que es lo que le permite al modelo chico acertar.
- Estilos en una sección nueva de [ui.css](front/src/styles/ui.css).

Cards de prompt precargado (las 3 confirmadas): *Generar recetas por área*,
*Generar desde plantilla `{...}`*, *Tabular mediciones de ensayo*. Cada card
no es un string: define operación + qué archivos pide, o sea que precarga el
formulario.

Progreso por etapas ("interpretando…" → "armando el plan…"), asumiendo que en
4 núcleos el modelo puede tardar.

## 7. Limpieza de `máquina232/` y `Diagramadora/`

La interfaz de edición de registros CSV dentro de la webapp **queda como está
hoy**. Lo que se borra son los directorios de las apps de escritorio, y recién
después de migrar lo que todavía vive solo ahí.

Estado (actualizado 2026-09-22, re-auditado al implementar esta fase):

1. ✅ **Hecho, en un plan propio**: `csv_recipe.py` + `recipe_editor.py`
   (editor de recetas tipo "matriz" vía round-trip a Excel) se migraron
   completos — motor, endpoints y pantalla nueva — según
   [`PLAN_EDITOR_RECETAS_MATRIZ.md`](PLAN_EDITOR_RECETAS_MATRIZ.md) (fases
   A-D), incluida la pantalla `/editor-recetas-matriz` con su card en
   Herramientas.
2. ✅ **Confirmado, sin acción**: `Diagramadora/universal.py`, `parser.py`,
   `excel_writer.py`, `main.py` son el conversor de ensayos Fuerza-Velocidad
   a Excel — exactamente lo que ya migraron `structure.py` / `labeler.py` /
   `generic_excel.py` / `llm.py`, expuesto hoy en la pantalla "Mediciones".
   `máquina232/src/app.py` (4150 líneas, la GUI Tkinter) y `_build_info.py`
   (artefacto de build) tampoco necesitan migración: reemplazados por el
   front web y por `version.py` respectivamente.
3. ✅ **Hecho**: reconciliados los tres archivos que divergían entre
   `máquina232/src` y `backend/app/core`:
   - `profile_builder.py` — se trajo la heurística más avanzada de
     `suggest_clave_row()` de máquina232 (fallback numérico +
     descarte de secuencias consecutivas + mejor-aproximado como último
     recurso), con 7 tests nuevos (`test_profile_builder_suggest_clave.py`)
     que fijan el comportamiento.
   - `excel_import.py` — la divergencia es una MEJORA del backend (lee CSV
     probando varios encodings — cp1252/latin-1 — en vez de solo utf-8-sig).
     Sin acción: máquina232 quedaría atrás, no al revés.
   - `paths.py` — divergencia deliberada y ya documentada; se confirmó que
     el comentario sigue siendo cierto (backend vive un nivel más hondo,
     `app/core/` vs `src/`, y tiene su propio `datos/` independiente a
     propósito).
4. ✅ Suite completa del backend corrida (416 tests, todos verdes).
5. ✅ **Hecho**: verificadas las referencias antes de borrar — ninguna
   funcional (nada en `build.bat`, specs de PyInstaller, imports); sí
   ~30 comentarios de procedencia tipo `(máquina232/src/app.py:2673)`
   repartidos en backend/front, a los que se les sacó la cita al archivo
   dejando el resto de la explicación. `máquina232/` y `Diagramadora/`
   borrados: los datos reales sin versionar que tenían adentro
   (`datos_reales_privados/`, `datos/`, `datos232/`, `respaldos_previos/`,
   `_backup_pre_universal/` — nunca estuvieron en git) se movieron fuera
   del repo antes de borrar. Los 175 archivos versionados quedaron
   borrados vía `git rm`, stageados junto al resto de esta sesión, **sin
   commitear todavía**.

## 8. Fases de implementación

Cada fase se puede verificar sola. La destructiva va al final a propósito.

| Fase | Qué | Listo cuando |
|---|---|---|
| 1 | ✅ `llama-server` persistente + fallback a subprocess | El labeler de mediciones sigue andando igual, y una llamada de prueba responde sin recargar el modelo |
| 2 | ✅ DSL: catálogo, gramática, intérprete, planificador | Tests: texto + contexto → programa esperado; programa → archivos byte-exactos |
| 3 | ✅ Endpoints `/api/asistente/{estado,interpretar,ejecutar}` + log | Se puede pedir el ejemplo de 3.2 por HTTP y baja el `.zip` correcto |
| 4 | ✅ Front: HoverCard, PlanCard, AsistentePanel, cards | Flujo completo en el navegador en las 3 pantallas |
| 5 | ✅ Validación de consistencia + auditoría | Detecta los dos defectos reales de la sección 5 |
| 6 | ✅ Migración pendiente + borrado de directorios | `profile_builder.py` migrado; `excel_import.py`/`paths.py` confirmados; `csv_recipe.py`/`recipe_editor.py` migrados completos vía `PLAN_EDITOR_RECETAS_MATRIZ.md`; `máquina232/` y `Diagramadora/` borrados (datos reales sin versionar movidos fuera del repo antes). Suite verde (416 tests), TypeScript limpio. Commiteado en `40c8c52`. |
| 7 | ✅ Asistente sobre los archivos de la pantalla (sección 12) | Verificado con el modelo real y en el navegador. En `/mediciones`, el pedido del 2026-09-23 con `824902015333_280826_006.csv` da dos hojas correctas; los ~120 CSV de H1312 se detectan como tablas y los `Prod.*.TXT` siguen por el motor de log; en Plantilla, "el campo de la línea N sale de la columna X" cambia los archivos generados. |

## 9. Tests

- **DSL**: cada operación fina por separado; programas compuestos; que un
  programa inválido se rechace antes de escribir nada.
- **Gramática**: que un encabezado inexistente sea *imposible* de emitir, no
  solo improbable. Es el test que sostiene el contrato de la sección 3.4.
- **Planificador**: batería de frases reales → programa esperado. Con el
  modelo real, marcados como lentos.
- **Equivalencia**: el programa que arma la card "Generar recetas por área"
  produce exactamente los mismos 54 archivos que
  `test_recetas_por_area_service.py`. Es la red que garantiza que el asistente
  no cambió el comportamiento de lo que ya funciona.
- **Validación**: los dos casos rotos de la sección 5 como fixtures.

## 10. Riesgos

- **El 1.5B puede no alcanzar** ni para la etapa de intención con texto muy
  libre. Mitigación: las cards cubren el grueso de los casos, y `desconocido`
  con slots vacíos siempre es una salida digna en vez de una adivinanza.
- **Latencia**: 4 núcleos sin GPU. Si un turno tarda demasiado incluso con el
  modelo residente, la salida es achicar `n_predict` y simplificar gramáticas.
- **Proceso huérfano** de `llama-server` si el backend se cae mal.
- **El DSL puede crecer sin control**; la regla de 3.1 existe para eso.
- **Falta probar el camino GPS1**: `Recetas_Andon.txt` no tiene ninguna fila
  de esa área.

## 11. Fuera de alcance

- Generación libre de contenido por parte del modelo (se decidió el DSL; se
  puede reconsiderar como fase 2 si aparecen casos que el DSL no cubra).
- Chat en las pantallas heredadas de máquina232.
- Cambiar el modelo o salir a una API externa.
- Multiusuario / identificación de quién generó qué.

## 12. Corrección (2026-09-23): el asistente trabaja sobre los archivos de la pantalla

Probado en `/mediciones`: el usuario describió la estructura de su CSV ("de la
fila 1 a la 12 es la primera tabla, la primera fila son los nombres de
columna; de la 14 a la 212 la otra; separador coma") y el asistente respondió
"Esta es la pantalla correcta: subí los archivos arriba". Se comportó como un
menú de navegación. Además el panel no recibía el archivo de la pantalla, y el
motor heurístico mezcló las dos tablas en una (199 registros × 135 campos).

Esto corrige dos decisiones de la sección 2:

- **Decisión 4** (la tabulación solo como operación gruesa): no alcanza.
  Mediciones y Plantilla tienen sus propias operaciones finas.
- **Decisión 7** (panel en las 3 pantallas): se mantiene, pero **cada panel
  trabaja sobre la tarea y los archivos de su pantalla**. Se elimina la etapa
  de intención (sección 3.3, etapa 1): la pantalla ya dice qué tarea es. Queda
  solo la etapa de parámetros, con una gramática por pantalla. Desaparecen
  `requiere_pantalla` y el "ir a otra pantalla".

### 12.1 Mediciones: CSV con varias tablas

Los CSV del equipo H1312 (`docs/H1312/`, unos 120 archivos) tienen bloques
separados por títulos (`[Auftragsdaten]`, `[Messprogrammseite 1]`,
`# QSStat`) y líneas vacías: un preámbulo y `[Auftragsdaten]` de pares
clave/valor, y dos tablas con encabezado. El encabezado de
`Messprogrammseite` tiene 8 nombres pero las filas traen 12 valores, y las
filas de `QSStat` terminan en coma.

- Motor nuevo determinista `app/ai/tablas_delimitadas.py`: detecta separador
  (lista cerrada: `,` `;` tab `|`), bloques y tipo de bloque (tabla con
  encabezado o clave/valor), y escribe **una hoja por bloque** con el nombre
  del título. Columnas sin nombre → `Columna N`; columna final vacía en todas
  las filas → se descarta; números → numéricos (salvo ceros a la izquierda).
- Las líneas de título nunca son encabezado ni dato. Si el usuario dice "la
  fila 1 es el encabezado" y la fila 1 es `[Messprogrammseite 1]`, se usa la
  siguiente y la tarjeta lo muestra. El usuario se puede equivocar en una
  fila; el sistema no debe copiar el error.
- Operaciones finas: `definir_tablas(tablas=[{desde, hasta, con_encabezado}])`
  y `usar_separador(separador)`. El modelo solo emite números de fila y un
  separador de la lista cerrada; los rangos se validan contra el archivo real.
  Lo que no dice el usuario sale de la detección automática, así que el
  programa final siempre está completo y queda en el log tal cual se ejecutó.
- La pantalla usa este motor también en su botón principal cuando el archivo
  tiene forma de tablas. Si no (los `Prod.*.TXT` de log, sin separadores),
  sigue el motor de siempre (`structure.discover`).
- Los nombres de columna se dejan como vienen del archivo: el labeler de IA
  queda para el formato de log.

### 12.2 Plantilla: indicaciones sobre qué columna llena cada campo

Hoy el motor decide qué columna del listado llena cada `{...}` leyendo el
comentario `// ...` de esa línea; si no matchea, la línea queda fija. Las
operaciones finas permiten decirlo en el chat:

- `asignar_columna(linea, columna)`: la línea N de la plantilla (solo líneas
  que tienen `{...}`) se llena con esa columna.
- `nombre_archivo_desde(columna)`.
- `filtrar_filas(columna, valor)`.

Las líneas posibles y las columnas son literales de la gramática, sacados de
los archivos subidos.

### 12.3 Front

- Cada pantalla le pasa sus archivos al panel. Las tarjetas de prompt son las
  de la pantalla (ej. en Mediciones: "La tabla 1 va de la fila X a la Y"), no
  el catálogo de todas.
- La tarjeta de Mediciones muestra cada tabla (título, filas, fila de
  encabezado, cantidad de columnas, primeros nombres) y es **editable**:
  desde/hasta/encabezado por tabla y quitar tablas, con "Actualizar vista
  previa" (sin IA). Después, "Generar Excel".
- Si el mensaje no trae ninguna indicación sobre el archivo (el programa
  final es igual al que se arma sin mensaje), la tarjeta lo dice y muestra
  lo que se hace sin indicaciones. El asistente no contesta preguntas sobre
  el sistema.

### 12.4 Lo que apareció al probar con el modelo real

- **Las gramáticas de parámetros nunca habían funcionado.** El parser GBNF
  de llama.cpp no acepta `_` en nombres de regla (`op_filtrar`,
  `lista_sufijos`...): `failed to parse grammar`, y el planificador caía en
  silencio al default. Los tests con modelo stub no lo veían. Reglas
  renombradas con `-` y un test que fija el alfabeto válido.
- **Con muchas opciones abiertas, el 1.5B divaga**: copiaba los números del
  ejemplo del prompt, filtraba por cualquier columna, deletreaba nombres de
  columna dentro del patrón, repetía operaciones hasta el tope de tokens.
  La solución fue la misma idea del contrato de la sección 3.4, un paso más
  fuerte: **en el plan solo puede entrar lo que el mensaje menciona**. Los
  números de fila, los sufijos, las columnas, los valores de filtro, los
  campos `#Codigo`/`#Descripcion` y las líneas de plantilla que admite la
  gramática son los que aparecen en el texto del usuario (y existen en el
  archivo); agrupar/nombrar/quitar notas solo si el mensaje lo pide con
  esas palabras. Sin nada mencionado, la única salida es `[]`. El patrón de
  nombre quedó como `{columna}<sep>...{sufijo}.def.txt`, sin letras libres.
- Una misma línea de plantilla asignada a dos columnas, o el nombre de
  archivo desde dos columnas, es un error visible en la tarjeta (antes
  ganaba la última). Un patrón de nombre sin `{sufijo}`, sin columna o con
  caracteres inválidos en Windows se rechaza en la validación.
- **Límite conocido**: con varias indicaciones en un mismo mensaje, en
  Recetas por área el modelo a veces aplica solo la primera (ej. los
  sufijos, pero no el filtro). La tarjeta muestra exactamente qué se va a
  hacer antes de generar. En Mediciones y Plantilla los pedidos compuestos
  probados salen completos.
