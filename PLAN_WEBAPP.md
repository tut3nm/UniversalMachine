# Unificación: Configurador de Planta + Conversor de Mediciones (FastAPI + React + pywebview)

> Estado: **plan aprobado, implementación aún no iniciada.**
>
> **Actualización 2026-08-31:** este documento vivía en `máquina232/webapp/PLAN.md`.
> La ubicación del proyecto nuevo se movió a la **raíz del monorepo**
> (`front/` y `backend/`, hermanas de `máquina232/` y `Diagramadora/`) en
> vez de anidarlo dentro de `máquina232/webapp/`. El resto del plan
> (arquitectura, reuso de `src/`, fases, wizard) sigue siendo válido tal
> cual — sólo cambian las rutas de la sección "Arquitectura" de abajo.

## Contexto

Hoy hay dos herramientas separadas para necesidades relacionadas pero distintas:

- **`máquina232`** (repo privado, `github.com/tut3nm/UniversalMachine`): app Tkinter madura (`ConfiguradorPlanta.exe`, 4.149 líneas en `app.py`, 228 tests) para **editar** archivos de "puesta a punto" de máquinas (recetas por producto), con un motor genérico dirigido por perfiles JSON (`profiles/maquina_*.json` + `src/datastore.py`), backups automáticos, historial auditable, deshacer/rehacer, detección de edición externa, wizard de alta de máquina, etc.
- **Diagramadora** (mismo monorepo, carpeta hermana): dos prototipos Tkinter — `universal.py` (tabula logs de ensayo a Excel, con IA local para nombrar columnas) y `recipe_editor.py` (edición básica de CSV tipo receta, **hoy redundante**: `ConfiguradorPlanta` hace lo mismo con muchísima más seguridad y pulido).

El pedido: un **único ejecutable**, con selector de modo (editar receta / tabular mediciones), con la IA **generando el perfil de formato de una máquina nueva** en vez de que un dev programe un parser a mano — y de paso, subir la ambición a un stack más profesional: **backend Python (FastAPI) + frontend TypeScript (shadcn/ui)**, empaquetados en un solo .exe con **pywebview**.

Decisiones ya tomadas con el usuario:
- El proyecto nuevo vive en `front/` y `backend/`, en la **raíz del monorepo** (mismo repo, mismo historial/CI) — `backend/` reutiliza `máquina232/src/` copiando esos módulos tal cual, igual que se planeaba cuando esto vivía anidado en `máquina232/webapp/`.
- `ConfiguradorPlanta.exe` (Tkinter) **sigue funcionando en paralelo** sin tocarse hasta que la app nueva tenga paridad de funciones (estrategia *strangler fig*, cero riesgo para planta mientras se construye).

Investigación ya hecha (relevada por agentes de exploración de Claude Code, no repetir): (a) la API pública completa de los 17 módulos de `máquina232/src/` (todos Python puro, sin Tkinter, listos para envolver) y (b) el flujo exacto del wizard de 4 pasos (`WizardMachineDialog`, `máquina232/src/app.py:503`) con referencias de línea. El detalle completo de ambos relevamientos queda documentado más abajo, en el Anexo.

## Arquitectura

```
UniversalMachine/                 (raíz del monorepo)
├─ máquina232/
│  └─ src/, profiles/, datos/, tests/, ...   (SIN TOCAR — ConfiguradorPlanta.exe sigue vivo)
├─ Diagramadora/
│  └─ ai/                          ← reutilizado tal cual por backend/app/ai/ (ver abajo)
├─ backend/
│  ├─ app/
│  │  ├─ main.py            FastAPI app + monta el frontend build + pywebview
│  │  ├─ core/               ← módulos de máquina232/src/ REUTILIZADOS (copiados, ver abajo)
│  │  ├─ routers/            maquinas.py, wizard.py, mediciones.py, backups.py, ...
│  │  ├─ services/           capa fina que adapta core/ a JSON (asdict, etc.)
│  │  └─ ai/                 ← ai/ de Diagramadora, tal cual (llm.py, structure.py, labeler.py, generic_excel.py)
│  └─ runtime/               ← runtime/ de Diagramadora, tal cual (llama.cpp + modelo, ~1 GB)
├─ front/                    Vite + React + TypeScript + shadcn/ui
│  └─ src/pages/             Dashboard, MaquinaDetalle, Wizard, Mediciones
├─ launcher.py                pywebview.create_window(...) + arranca uvicorn en un thread
└─ build.bat                  npm run build (frontend) → PyInstaller --onedir (backend + frontend build + runtime)
```

**Por qué `--onedir` y no `--onefile`:** ya lo probamos con el Conversor Universal (Diagramadora) — con ~1 GB de modelo de IA embebido, `--onefile` fuerza a re-descomprimir todo en cada arranque (15-40s de demora). `--onedir` (carpeta autocontenida) arranca en segundos. Mismo patrón que `Conversor_Universal_IA/`.

**Modelo de proceso:** un solo proceso Python. `launcher.py` arranca uvicorn (FastAPI) en un thread de fondo sobre `127.0.0.1:<puerto>`, y abre una ventana pywebview apuntando ahí. FastAPI sirve tanto la API (`/api/...`) como los archivos estáticos ya compilados del frontend (`StaticFiles` + fallback SPA). No hace falta Node en la PC del operario — el build de React se hace una vez, en desarrollo, y se empaqueta.

## Reutilización de `máquina232/src/` — regla general

Los 17 módulos de negocio (`profile.py`, `datastore.py`, `metadata.py`, `io_seguro.py`, `validacion.py`, `backups.py`, `historial.py`, `informe.py`, `diferencias.py`, `salud.py`, `panel_multi_maquina.py`, `filtros.py`, `excel_import.py`, `import_mapeos.py`, `importacion.py`, `arranque.py`, `deteccion_externa.py`) se **copian tal cual** a `backend/app/core/` (no se reescriben) y cada router de FastAPI los llama directo. Son Python puro, ya devuelven dicts/dataclasses — sólo hace falta `dataclasses.asdict()` en el borde de la API (y `.isoformat()` para el único campo `datetime`, en `BackupInfo`).

Los tests puros (`test_engine.py`, `test_synthetic.py`, `test_datastore_indice.py`, `test_profile_validacion.py`, `test_validacion.py`, `test_io_seguro.py`, `test_metadata.py`, `test_backups.py`, `test_historial.py`, `test_informe.py`, `test_diferencias.py`, `test_deteccion_externa.py`, `test_salud.py`, `test_panel_multi_maquina.py`, `test_filtros.py`, `test_excel_import.py`, `test_import_mapeos.py`, `test_importacion.py`, `test_arranque.py` — ~19 archivos) se copian a `backend/tests/` y corren **sin cambios** contra `core/`: son la red de seguridad heredada.

Los `test_app_*.py` (integración vía Tkinter real) **no** se portan — documentan comportamientos (orden autosave→backup, semántica de deshacer, recuperación de corrupción) que hay que re-cubrir con tests de integración nuevos contra los endpoints FastAPI, en Fase 2.

### Los 4 módulos que SÍ necesitan un ajuste de diseño (no una reescritura)

1. **`instancia.py`** (lock por PID): el supuesto "un proceso = un operario" ya no aplica igual con HTTP. Como el modelo de despliegue sigue siendo "un .exe por PC" (no se vuelve multiusuario en red), alcanza con simplificar: un lock a nivel de **todo el proceso** (no por máquina) al arrancar `launcher.py` — sigue evitando que se abran dos `.exe` a la vez en la misma PC, igual que hoy, sin necesitar granularidad por pestaña del navegador.
2. **`historial.py`**: `registrar()` usa `getpass.getuser()` — pasar el usuario explícito desde la capa de servicio (que por ahora también puede ser `getpass.getuser()` del lado del backend, ya que sigue siendo un solo operario por PC; dejar el parámetro explícito para no cerrar la puerta a autenticación real más adelante).
3. **`deteccion_externa.py`**: el "hash conocido" pasa de ser una variable en memoria de la app a un valor que el **frontend** debe recibir en cada `GET` y reenviar en el siguiente `POST` (patrón tipo ETag/If-Match). El backend lo compara antes de guardar.
4. **`excel_import.py`**: `abrir_archivo_importacion(path)` espera una ruta; agregar un adaptador que reciba un `UploadFile` de FastAPI, lo escriba a un temp file (o lo pase como file-like — `csv.reader` y `openpyxl` ya aceptan ambos) y delegue en la función existente.

## Ámbito de la Fase 1 (lo que se construye ahora)

**Backend (FastAPI):**
- `core/` = los 17 módulos copiados + los 4 ajustes de arriba.
- `routers/maquinas.py`: listar perfiles (`GET /api/maquinas`, envuelve `panel_multi_maquina.resumen_de_todas`), activar/cargar una máquina, listar/crear/editar/borrar registros (`DataStore` + `validacion`), guardar (autosave con `backups.crear_backup` antes de sobrescribir, igual que hoy).
- `routers/wizard.py`: implementa el flujo de 5 llamadas que salió del relevamiento del agente —
  `POST /wizard/start` (sube CSV, corre `profile_builder.sniff_csv`+`read_grid`) →
  `POST /wizard/classify-rows` (corre `classify_row`/`suggest_clave_row`/`suggest_tipo` por fila/columna — el equivalente exacto de `_build_row_state`, `app.py:764`) →
  **acá se agrega el hook de IA** (ver abajo) →
  `POST /wizard/build-profile` (arma `campos_elegidos`/`row_kinds` y llama `profile_builder.build_profile_columnas`/`build_profile_filas`) →
  `POST /wizard/validate` (repite el Paso 4 exacto: `Profile.from_dict` → `DataStore.load` → `to_text().encode()` → comparación byte a byte contra el original — **esta validación es la que decide si el botón "Confirmar" se habilita, igual que hoy; no se toca este invariante**) →
  `POST /wizard/confirm` (escribe el perfil + siembra `datos/<id>/` en modo alta, o backup+overwrite del JSON en modo edición — replica `_on_confirm`, `app.py:1230`).
- `routers/mediciones.py`: envuelve `ai/structure.py` (`discover`), `ai/labeler.py` (`build_labels`), `ai/generic_excel.py` (`write_excel`) de Diagramadora — subida de archivo(s), progreso, descarga del Excel resultante. Es el equivalente de `universal.py` de hoy, ahora como endpoints.
- `routers/backups.py`, `historial.py`, `salud.py`, `diferencias.py`: exponer lo mínimo para que el frontend los muestre (lectura), sin todavía restaurar/deshacer desde la UI nueva — eso es Fase 2 (ver abajo). Guardar SÍ crea backup automático desde el día 1 (no es opcional, es el mecanismo de seguridad ya probado).

**Dónde entra la IA — dos puntos concretos, mismo runtime que ya está probado (`ai/llm.py`, gramática GBNF):**
1. **Wizard, entre `classify-rows` y `build-profile`**: dado el grid clasificado + (opcional) un archivo de anotaciones, la IA propone `titulo_ui` humanizado y afina `tipo`/`formato` para las filas/columnas marcadas como "dato". Es una extensión de `profile_builder.suggest_tipo`, no un reemplazo: la clasificación fija/índice/dato/clave sigue siendo 100% determinística (ya funciona bien, no hace falta IA ahí). El ingeniero ve las sugerencias precargadas en la tabla del Paso 3 y las edita como ya hace hoy. El botón de confirmar sigue bloqueado hasta que `/wizard/validate` dé bytes idénticos — la IA nunca puede colar un perfil que no reconstruya el archivo real.
2. **Mediciones**: igual que hoy en `universal.py` — nombra columnas a partir del archivo de anotaciones (o prolija nombres crudos si no hay anotaciones), nunca toca los números.

**Frontend (React + TypeScript + shadcn/ui, Vite):**
- `Dashboard`: lista de máquinas (`panel_multi_maquina`), botón "Agregar máquina", selector de modo (Recetas / Mediciones).
- `MaquinaDetalle`: tabla de registros (shadcn `Table` o `DataTable` con TanStack Table), búsqueda simple, alta/edición/borrado de registro (formulario con validación de rango vía `validacion.py`).
- `Wizard`: los mismos 4 pasos, con el paso 3 mostrando las sugerencias de la IA como valores precargados editables, y el paso 4 mostrando el resultado de `/wizard/validate` (verde/rojo, igual que hoy).
- `Mediciones`: subir archivo(s), barra de progreso, tabla de resultado + botón descargar Excel.

**Empaquetado:** `launcher.py` (pywebview) + `build.bat` nuevo (build de frontend con `npm run build`, luego PyInstaller `--onedir` incluyendo `backend/app`, el build de `front/dist`, y `backend/runtime/`). Instalar `pywebview` (confirmado disponible, `pip install pywebview`; Node/npm ya están instalados, v24/11.6).

## Fase 2 (explícitamente NO se construye ahora — roadmap)

Paridad completa con `ConfiguradorPlanta`: deshacer/rehacer en sesión, edición en línea/masa, diálogo de Backups (restaurar con preview de diferencias), diálogo de Historial (filtros + exportar CSV), diálogo de Salud, diálogo de Duplicados, Filtros avanzados guardados, detección de modificación externa integrada a la UI (patrón ETag ya dejado listo en el backend), instancia única. Cada uno de estos ya tiene su módulo de backend probado (Fase 1 los deja listos para envolver) — Fase 2 es mayormente trabajo de frontend + tests de integración nuevos, no lógica nueva.

## Qué pasa con lo existente de Diagramadora

- `ai/structure.py`, `ai/labeler.py`, `ai/generic_excel.py`, `ai/llm.py`: se **mueven** a `backend/app/ai/` (reuso directo, ya validados contra el archivo real de 208.478 mediciones).
- `Diagramadora/runtime/` (llama.cpp + modelo Qwen): se **copia** a `backend/runtime/`.
- `recipe_editor.py` y `ai/csv_recipe.py` (de Diagramadora): se **retiran** — `ConfiguradorPlanta`/el sistema nuevo los reemplaza con ventaja. No se portan.
- `main.py`/`parser.py`/`excel_writer.py` (el conversor específico de amortiguadores) y `universal.py` (de Diagramadora): quedan como están, ya entregados; no hace falta tocarlos — la lógica que importa (`ai/`) se reutiliza desde el sistema nuevo.

## Verificación

1. **Backend:** correr los ~19 archivos de test puros portados (`pytest backend/tests/`) — deben pasar sin modificaciones de lógica, solo de import path. Esto confirma que `core/` no perdió ninguna garantía (escritura atómica, validación de perfil, backups, etc.).
2. **Wizard end-to-end:** repetir la prueba manual con `recetas232.csv` contra `POST /wizard/*` en secuencia — confirmar que `/wizard/validate` da `ok=true` con bytes idénticos, igual que hoy hace el wizard de Tkinter.
3. **IA en el wizard:** con y sin archivo de anotaciones, confirmar que las sugerencias de `titulo_ui` aparecen precargadas y que el usuario puede sobreescribirlas antes de `build-profile`.
4. **Mediciones:** repetir la prueba ya hecha (208.478 mediciones, 5.000 comparadas campo a campo) contra el endpoint nuevo, mismo resultado que `universal.py` standalone.
5. **Empaquetado:** build completo (`npm run build` + `build.bat`), lanzar el `.exe` resultante desde una carpeta aislada (mismo test que se hizo con `Conversor_Universal_IA`), confirmar que abre sin consola negra y sin depender de nada fuera de su propia carpeta.
6. **No regresión sobre lo existente:** `ConfiguradorPlanta.exe` (Tkinter) se re-compila y se prueba igual que siempre — cero cambios en `máquina232/src/`, así que no debería haber ninguna diferencia; correr su suite completa (`pytest`, 228 tests) como confirmación de que no se tocó nada por error.

---

## Anexo A — Mapa de módulos reutilizables de `máquina232/src/` (relevado antes de planificar)

**Bottom line:** todos son Python puro (cero Tkinter/ttkbootstrap), toman y devuelven dicts/dataclasses/listas/primitivos, operan sobre **rutas de archivo** para load/save. `DataStore`/`Profile` son los únicos objetos con estado, y son objetos Python comunes (no singletons globales) — envolubles por request o cacheables por máquina en la capa de servicio.

- **profile.py** — `ProfileError`, `Campo` (dataclass), `Profile` (dataclass: `.load(path)`, `.from_dict(data)`, `campo_clave()`, `parametros()`, `campos_visibles()`, `parametros_visibles()`, `campo_por_nombre()`, `placeholder_regex()`, `placeholder_template()`, `duplicados_config()`). Validación automática al cargar (`ProfileError`).
- **datastore.py** — el motor. `DataStore(profile, records=None, raw_cells=None)` o `DataStore.load(path, profile)`. Save: `to_grid()`, `to_text()`, `save(path)` (atómico). CRUD: `nuevo_registro()`, `add()`, `update()`, `delete()`, `find_key()` (O(1) vía índice). Helpers: `key_of()`, `is_placeholder()`, `count_real()`, `find_similar_groups()`. Estado en memoria (`self.records`) hasta `save()` explícito.
- **metadata.py** — `Sidecar` (meta.json): `.load(path)` (auto-cuarentena si está corrupto), `.save(claves_validas=None)`, `get/set/keys_with/rename_key`.
- **io_seguro.py** — `escribir_atomico`, `escribir_bytes_atomico`, `copiar_atomico`, `verificar_contenido`. Sin estado, solo I/O.
- **validacion.py** — `ErrorValidacion` (dataclass), `validar_valor_numerico`, `parsear_valor_campo`, `validar_valores_de_registro`.
- **backups.py** — `BackupInfo` (dataclass, tiene un campo `datetime`), `crear_backup`, `listar_backups`, `verificar_integridad`, `restaurar_backup`, `purgar_backups`, `resumir_diferencias(store_actual, store_backup)`.
- **historial.py** — `EventoHistorial` (dataclass + `.to_dict()`), `registrar(...)` (usa `getpass.getuser()` — ajustar), `leer_eventos`, `rotar_si_hace_falta`, `purgar_eventos_viejos`.
- **informe.py** — `a_filas_csv(eventos)`: shaping de historial a filas CSV.
- **diferencias.py** — `comparar_con_original(store_actual, store_original)`, `filtrar_por_tipo`, `a_filas_csv`.
- **deteccion_externa.py** — `hash_archivo(path)`, `fue_modificado_externamente(path, hash_conocido)` — el "hash conocido" hoy vive en memoria de la app; en la API pasa a ir y volver con el cliente (patrón ETag).
- **instancia.py** — lock de instancia única por PID (`InstanciaBloqueadaError`, `adquirir`, `liberar`) — **no portable tal cual**, es el único módulo que necesita rediseño de concepto (ver Fase 1).
- **salud.py** — `Hallazgo` (dataclass), `evaluar_salud(store, sidecar)`, `contar_slots_libres`.
- **panel_multi_maquina.py** — `ResumenMaquina` (dataclass), `resumen_de_maquina(profile)`, `resumen_de_todas(profiles)` — ya es, en esencia, el endpoint del dashboard.
- **filtros.py** — `coincide_busqueda`, `coincide_rangos`, `filtrar`, `cargar_guardados/guardar_lista/agregar_o_reemplazar/eliminar` (presets por máquina).
- **excel_import.py** — `open_workbook`, `WorkbookCSV`, `abrir_archivo_importacion(path)` (espera ruta — necesita adaptador a `UploadFile`), `guess_mapping_generic`, `read_rows_generic`, normalizadores (`normalize_code/int/decimal/value`, `tuvo_decimales`).
- **import_mapeos.py** — `cargar/guardar/aplicar_a_headers` (recuerda el último mapeo de columnas por máquina, por texto de encabezado).
- **importacion.py** — `calcular_diferencias(store, profile, mapped_fields, rows)` → diffs/altas/obsoletos/sin cambios. Ya desacoplado de la UI.
- **arranque.py** — `seed_or_migrate`, `migrate_legacy_232` — side-effects sobre disco, sin valor de retorno; mapea a un endpoint de "activar máquina".
- **paths.py** — `resource_path`, `app_base_dir`, `profiles_dir`, `data_dir_for` — resolución de rutas dev vs. empaquetado (mismo patrón `sys._MEIPASS`/`sys.frozen` usado en Diagramadora).

**Grafo de dependencias (quién llama a quién):** `datastore.py` es el hub — lo consumen `validacion` (indirecto), `salud`, `diferencias`, `importacion`, `backups.resumir_diferencias`, `panel_multi_maquina`, `arranque`. `profile.py` (`Campo`/`Profile`) es el vocabulario compartido por casi todos. `metadata.Sidecar` lo usan `salud`, `panel_multi_maquina`, `arranque`.

**Tests (31 archivos, 228 tests):** ~19 son unitarios puros (portan sin cambios: `test_engine`, `test_synthetic`, `test_datastore_indice`, `test_profile_validacion`, `test_validacion`, `test_io_seguro`, `test_metadata`, `test_backups`, `test_historial`, `test_informe`, `test_diferencias`, `test_deteccion_externa`, `test_salud`, `test_panel_multi_maquina`, `test_filtros`, `test_excel_import`, `test_import_mapeos`, `test_importacion`, `test_arranque`). El resto son `test_app_*.py` (integración vía Tkinter real, no portan tal cual — documentan comportamiento a re-cubrir en Fase 2) + `conftest.py` (aísla tests que instancian la App real en subprocesos, por el singleton `Style` de ttkbootstrap).

## Anexo B — Flujo exacto del wizard (`WizardMachineDialog`, `máquina232/src/app.py:503`)

Motor de soporte: `profile_builder.py`. Relacionados: `profile.py` (`Profile`, `ProfileError`), `datastore.py` (`DataStore`), `paths.py`.

**Entradas:** Alta → `WizardMachineDialog(parent, existing_ids)` (línea 458). Edición → `WizardMachineDialog(parent, existing_ids, existing_profile=prof)` (línea 479). Resultado en `dlg.new_profile` tras cerrar el modal.

### Paso 1 — identidad + archivo de muestra (`_show_step_archivo` L613, `_on_step1_continue` L676)
- Entrada: `id`, `nombre`, `descripcion` (opcional), CSV subido.
- `id` se slugifica y se valida contra `existing_ids`.
- `profile_builder.sniff_csv(path)` (L33) → `{bom, fin_de_linea, delimitador, simbolo_decimal}` (lee 64KB, detecta BOM/CRLF-CR-LF/delimitador vía `csv.Sniffer`, hint de símbolo decimal si aparece "Decimal symbol=" en la muestra).
- `profile_builder.read_grid(path, delimitador)` (L60) → grilla cruda completa.
- Estado que pasa al paso siguiente: `machine_id, nombre, desc, csv_path, info, grid`.
- Equivalente REST: `POST /wizard/start` — recibe el archivo, devuelve `{info, grid_preview}` + un id de sesión de wizard (la grilla completa se guarda del lado del servidor, no conviene ida y vuelta completa con el cliente si el archivo es grande).

### Paso 2 — orientación (`_show_step_orientacion` L706, `_on_step2_continue` L740)
- Usuario elige `orientacion`: `"filas"` (CSV normal, un registro por fila) o `"columnas"` (transpuesto, como la 232). Default `"columnas"`.
- Vista previa: primeras 12 filas — puramente de render en el front, no necesita otra llamada si el paso 1 ya devolvió la grilla.
- Al continuar dispara `_build_row_state()` (L764) — es en realidad la preparación del Paso 3.

### Clasificación de filas/columnas — `_build_row_state` (L764)
Para cada índice del eje (filas si `orientacion="columnas"`, columnas si `orientacion="filas"`):
- `kind` (`profile_builder.classify_row`, L69): `"indice"` si es secuencia ascendente de a 1 (&gt;2 valores), `"fija"` si todos los valores son iguales o vacíos, si no `"dato"`. **Excepción:** una fila *después* de la clave nunca se auto-sugiere `"fija"` (se fuerza a `"dato"`, para no arriesgar el ancho de fila si mañana varía) — el usuario puede igual forzarla a mano.
- Clave sugerida (`profile_builder.suggest_clave_row`, L98, solo orientación columnas): primera fila con valores no numéricos y todos distintos entre sí. Default `0` si no hay ninguna.
- Tipo sugerido (`profile_builder.suggest_tipo`, L126): `"entero"`/`"entero_ceros"` (con `formato.ancho`) si todo matchea `^[+-]?\d+$`; si no, prueba separador decimal (hint primero, después `,` y `.`) → `"decimal"` con `formato.separador_decimal`/`decimales`; si nada matchea → `"texto"` (fallback seguro, nunca pierde datos).
- `incluir` por defecto: `True` si es la clave sugerida o `kind=="dato"`.
- Cada fila queda con: `kind, etiqueta, muestra, incluir, nombre, titulo, tipo, ancho/decimales/separador, kind_override` (más `_min/_max/_default`, solo en modo edición).
- Equivalente REST: `POST /wizard/classify-rows` — devuelve, por índice de eje: `{idx, etiqueta, muestra, kind, incluir_default, nombre_default, titulo_default, tipo_sugerido, formato_sugerido, kind_override_default}` + `clave_sugerida`. El frontend es dueño de las ediciones locales hasta el submit.

### Paso 3 — tabla de campos (`_show_step_campos` L899, `_on_step3_continue` L1050)
- Columnas de la tabla: Clave (radio, una sola), Incluir (checkbox), Etiqueta detectada (con badge `[fija]`/`[índice]`/`[existente]`), Nombre interno, Título, Tipo (dropdown), Formato (widgets dinámicos según tipo), "Si no es campo" (oculto/fila fija/fila índice — solo orientación columnas, deshabilitado si `incluir` está tildado), Muestra.
- Construcción de `campos_elegidos` (L1050):
  1. Fila/columna clave → siempre incluida, `rol:"clave"`, `tipo:"texto"` forzado.
  2. Filas excluidas (`incluir=False`) → en orientación columnas, `row_kinds[idx] = kind_override` (oculto/fija/índice); en filas, cae directo a "columna oculta".
  3. Filas incluidas → validación de `nombre` (slug único, si falla aborta con aviso) y de `formato` (ancho/decimales válidos, si falla aborta con aviso), se agregan a `campos_elegidos` con `min/max/default` (estos tres solo se completan en modo edición, no hay widget para editarlos en este wizard).
  4. `features` se remapea (`_remaped_features`, L1031): en edición, copia `features` del perfil existente (ej. config de duplicados) y actualiza el nombre de campo clave si cambió.
  5. Llama `profile_builder.build_profile_columnas`/`build_profile_filas` (según orientación), con try/except `(ValueError, ProfileError)` — si falla, se queda en el paso 3 mostrando el error.
- `build_profile_columnas`/`build_profile_filas` (`profile_builder.py:174-363`) recorren TODA la grilla (no solo lo elegido): la clave → `rol:"clave"`; lo elegido → `rol:"parametro"` visible; lo no elegido con `kind_override` (o re-clasificado) → `filas_fijas`/`fila_indice`; el resto → campo oculto (`visible:False`) para no perder ninguna celda del archivo original.
- Equivalente REST: `POST /wizard/build-profile` — recibe `{wizard_id, clave_idx, orientacion, rows: [...]}`, reconstruye `campos_elegidos`/`row_kinds` server-side (misma validación: slugs únicos, ancho/decimales), llama `build_profile_columnas`/`build_profile_filas`, devuelve el perfil dict (sin persistir todavía) o errores 400.

### Paso 4 — validación byte-perfecta (`_show_step_validar` L1148, `_on_confirm` L1230)
- Al entrar al paso (no requiere acción del usuario):
  1. `Profile.from_dict(perfil_dict)` (puede lanzar `ProfileError`).
  2. `DataStore.load(csv_path, prof)` — carga el archivo de muestra **con el perfil recién armado**.
  3. Lee los bytes originales.
  4. `store.to_text().encode(prof.encoding)` — reserializa.
  5. Compara byte a byte.
  6. `n_registros = len(store.records)`.
  - Cualquier excepción (`ValueError, ProfileError, OSError, UnicodeDecodeError`) → `ok=False` + mensaje.
- **El botón Confirmar queda deshabilitado mientras `ok != True`.** Sin excepción, sin "confirmar de todos modos". Único camino: volver al paso 3, ajustar tipos/formatos u ocultar más columnas, y se re-valida solo al volver a este paso.
- Si cambió la fila/columna clave (modo edición): aviso ámbar + confirmación extra (las marcas de "no es duplicado" quedan huérfanas).
- Equivalente REST: `POST /wizard/validate` — corre los mismos pasos 1-6 server-side, devuelve `{ok, n_registros, n_visibles, n_ocultos, error_msg, primer_diff_byte, orig_len, regen_len}`. El botón "Confirmar" del frontend se habilita solo con `ok===true`, replicando el comportamiento actual.

### Confirmar (`_on_confirm`, L1230)
**Alta:** perfil nuevo en `profiles/maquina_<id>.json` (si ya existe, aborta — guarda contra condición de carrera) vía `escribir_atomico`; `data_dir = paths.data_dir_for(id)`; copia atómica del CSV subido a `original.<ext>` y `actual.<ext>` (así se "siembra" `datos/<id>/` — no hay una función de seed separada acá, `arranque.py` no interviene en el wizard).

**Edición:** backup del JSON existente (`.bak-<timestamp>`) + sobrescritura atómica del perfil. **No** toca `actual.csv`/`original.csv` — edición solo reescribe el perfil.

Equivalente REST: `POST /wizard/confirm` — alta escribe perfil + siembra `datos/<id>/`; edición hace backup + overwrite del JSON solamente. Ambos deben re-correr la validación de `/wizard/validate` server-side como guarda final (no confiar en un `ok` stale del cliente), y alta debe re-chequear que el `profile_path` no exista todavía (condición de carrera).

### Diferencias en modo edición
- Constructor salta Paso 1 y 2: `_load_existing_profile` (L573) va directo al Paso 3.
- Archivo fuente = `datos/<id>/actual.<ext>` (el vigente, no uno resubido — "es el que no se puede corromper").
- Pre-población de filas: `_build_row_state_from_profile` (L805) — cada índice se busca primero en el perfil existente (`kind` = `"campo"`/`"fija"`/`"indice"`, badge "existente"); solo lo nuevo desde el último guardado cae a auto-detección fresca.
- `_clave_idx_original` (L827) detecta si el usuario cambia la clave (`_clave_changed`) → aviso extra en Paso 4, no existe en modo alta.
- Botón "Atrás" a Paso 2 oculto (no hay paso de orientación que revisitar).
- Persistencia: backup+overwrite del JSON solamente (vs. escribir JSON + sembrar `datos/<id>/` en alta).
- Equivalente REST: sesión de wizard en modo edición se inicia con `POST /wizard/start?profile_id=X` (carga y snifea `actual.<ext>` server-side, salteando pasos 1-2 en el cliente) vs. `POST /wizard/start` (alta, espera un archivo subido). Ambos convergen en la misma secuencia `/wizard/classify-rows` → `/wizard/build-profile` → `/wizard/validate` → `/wizard/confirm`, con `/wizard/confirm` bifurcando internamente según sea alta o edición.
