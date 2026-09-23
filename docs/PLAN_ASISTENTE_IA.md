# Plan: asistente conversacional con IA local + DSL de operaciones

> Estado: PLANIFICADO, sin implementar. Surge de la conversación de diseño del
> 2026-09-22. Las decisiones de la sección 2 ya están tomadas; lo que quede
> abierto está marcado **(TBD)**.

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
| 6 | ✅ Migración pendiente + borrado de directorios | `profile_builder.py` migrado; `excel_import.py`/`paths.py` confirmados; `csv_recipe.py`/`recipe_editor.py` migrados completos vía `PLAN_EDITOR_RECETAS_MATRIZ.md`; `máquina232/` y `Diagramadora/` borrados (datos reales sin versionar movidos fuera del repo antes). Suite verde (416 tests), TypeScript limpio. Falta solo el commit del borrado, a criterio del usuario. |

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
