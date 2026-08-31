# Graph Report - .  (2026-08-31)

## Corpus Check
- cluster-only mode — file stats not available

## Summary
- 914 nodes · 2022 edges · 37 communities (33 shown, 4 thin omitted)
- Extraction: 91% EXTRACTED · 9% INFERRED · 0% AMBIGUOUS · INFERRED: 175 edges (avg confidence: 0.63)
- Token cost: 0 input · 0 output

## Graph Freshness
- Built from commit: `2aba6876`
- Run `git rev-parse HEAD` and compare to check if the graph is stale.
- Run `graphify update .` after code changes (no API cost).

## Community Hubs (Navigation)
- App
- profile.py
- WizardMachineDialog
- .from_dict
- DataStore
- app.py
- test_filtros.py
- test_historial.py
- Sidecar
- test_importacion.py
- test_instancia.py
- Configurador de Parámetros de Planta
- test_excel_import.py
- test_validacion.py
- profile_builder.py
- test_backups.py
- test_io_seguro.py
- test_panel_multi_maquina.py
- import_mapeos.py
- Campo
- hash_archivo
- Profile
- _center_dialog
- excel_import.py
- _normalizar_separador_decimal
- HistorialDialog
- test_informe.py
- graphify-out/graph.json
- log_config.py
- MachineSelector
- datastore.py
- WorkbookCSV
- SaludDialog
- DeleteMachineDialog
- .iter_rows
- Pattern

## God Nodes (most connected - your core abstractions)
1. `DataStore` - 90 edges
2. `App` - 66 edges
3. `Profile` - 65 edges
4. `Campo` - 39 edges
5. `Sidecar` - 33 edges
6. `WizardMachineDialog` - 32 edges
7. `ProfileError` - 28 edges
8. `ejecutar_test_en_subproceso_aislado()` - 26 edges
9. `button()` - 25 edges
10. `en_subproceso_aislado()` - 25 edges

## Surprising Connections (you probably didn't know these)
- `test_resumir_diferencias_detecta_perdidas_recuperos_y_cambios()` --calls--> `DataStore`  [INFERRED]
  tests/test_backups.py → src/datastore.py
- `test_resumir_diferencias_sin_cambios()` --calls--> `DataStore`  [INFERRED]
  tests/test_backups.py → src/datastore.py
- `_store()` --calls--> `DataStore`  [INFERRED]
  tests/test_importacion.py → src/datastore.py
- `test_guardar_con_fila_fija_mas_ancha_que_los_datos_falla_explicitamente()` --calls--> `DataStore`  [INFERRED]
  tests/test_integridad_grid.py → src/datastore.py
- `test_guardar_normal_no_se_ve_afectado_por_la_verificacion()` --calls--> `DataStore`  [INFERRED]
  tests/test_integridad_grid.py → src/datastore.py

## Import Cycles
- None detected.

## Hyperedges (group relationships)
- **Graphify Query-Update Workflow** — claude_graphify_query, claude_graphify_path, claude_graphify_explain, claude_graphify_update [INFERRED 0.75]

## Communities (37 total, 4 thin omitted)

### Community 0 - "App"
Cohesion: 0.05
Nodes (31): App, CambioRegistro, _cargar_perfiles(), confirm(), error(), info(), main(), preguntar_opciones() (+23 more)

### Community 1 - "profile.py"
Cohesion: 0.06
Nodes (68): app_base_dir(), data_dir_for(), profiles_dir(), paths.py ======== Ubicación de recursos (perfiles, archivos de datos) tanto en…, Ruta a un recurso embebido (funciona con PyInstaller y en desarrollo)., Carpeta escribible: junto al .exe (empaquetado) o raíz del proyecto., Carpeta escribible de perfiles, sembrada desde los perfiles embebidos. Los…, resource_path() (+60 more)

### Community 2 - "WizardMachineDialog"
Cohesion: 0.06
Nodes (24): Combobox, Frame, build_scrollable_canvas(), button(), DiffsDialog, DuplicatesDialog, FiltrosDialog, ImportDialog (+16 more)

### Community 3 - ".from_dict"
Cohesion: 0.06
Nodes (67): parametrize, _perfil(), _perfil_columnas_232(), Tests de src/arranque.py (seed_or_migrate / migrate_legacy_232), extraído de…, Formato transpuesto real de la 232: cada registro es una columna, el código…, test_migracion_legado_232_copia_datos_y_marcas_de_revisado(), test_seed_con_archivo_inicial_copia_ambos_destinos(), test_seed_sin_archivo_inicial_crea_catalogo_vacio() (+59 more)

### Community 4 - "DataStore"
Cohesion: 0.06
Nodes (49): DataStore, Colección de registros de un archivo, con carga/guardado fiel al formato…, Todas las filas del archivo final deben tener el mismo ancho: un CSV con filas…, Texto a escribir para la celda de `campo` en el registro `index`: el string…, Escritura atómica (ver io_seguro.py): el archivo destino nunca queda a medio…, Crea un registro con los defaults del perfil, pisados por `valores`., Agrupa índices de registros reales cuya firma coincide (según el método de…, a_filas_csv() (+41 more)

### Community 5 - "app.py"
Cohesion: 0.08
Nodes (36): apply_theme(), enable_dpi_awareness(), app.py — Configurador de Parámetros de Planta…, Registra y aplica el tema propio 'planta' (verde hoja / blanco / gris) sobre la…, migrate_legacy_232(), Seed y migración de datos al activar una máquina por primera vez. Extraído de…, seed_or_migrate(), BackupInfo (+28 more)

### Community 6 - "test_filtros.py"
Cohesion: 0.09
Nodes (19): agregar_o_reemplazar(), cargar_guardados(), coincide_busqueda(), coincide_rangos(), eliminar(), filtrar(), guardar_lista(), Búsqueda y filtros avanzados (Nivel 4.7 del plan de mejoras). Antes, la barra… (+11 more)

### Community 7 - "test_historial.py"
Cohesion: 0.10
Nodes (18): EventoHistorial, leer_eventos(), purgar_eventos_viejos(), datetime, historial.py ============ Registro append-only de cambios…, Si el historial activo superó TAMANO_MAX_BYTES, archiva TODO su contenido a un…, Archiva (comprime, NO borra el contenido) los eventos más viejos que `dias` a…, Agrega una línea al historial. Es un append: no reescribe el archivo entero (a… (+10 more)

### Community 8 - "Sidecar"
Cohesion: 0.10
Nodes (19): Todas las claves cuyo `flag` está en True., Si un código cambia de nombre, mover sus flags con él., Renombra el archivo dañado a `<path>.corrupto-<timestamp>` en vez de…, Guarda el sidecar. Si se pasa `claves_validas` (las claves que existen HOY en…, Sidecar, test_metadata.py — Sidecar de metadatos, incluyendo manejo de corrupción (Nivel…, Tras save(claves_validas=...), el propio objeto Sidecar (sin recargar desde…, Tras detectar la corrupción, el sidecar debe quedar 100% operativo: se pueden… (+11 more)

### Community 9 - "test_importacion.py"
Cohesion: 0.14
Nodes (24): calcular_diferencias(), Cálculo de diferencias entre el catálogo cargado y filas leídas de un Excel de…, Compara `rows` (ya leídas del Excel, sin normalizar) contra `store.records`.…, ErrorValidacion, _fmt(), parsear_valor_campo(), validacion.py ============= Validación de valores de un registro contra las…, Valida un valor YA TIPADO (int/float) de un campo numérico contra el min/max… (+16 more)

### Community 10 - "test_instancia.py"
Cohesion: 0.10
Nodes (13): Exception, adquirir(), InstanciaBloqueadaError, leer_lock(), liberar(), _lock_path(), _proceso_vivo(), Instancia única por máquina (Nivel 4.4 del plan de mejoras). Aun con un .exe… (+5 more)

### Community 11 - "Configurador de Parámetros de Planta"
Cohesion: 0.10
Nodes (25): app.py, build.bat, Byte-perfect File Reconstruction, Configurador de Parámetros de Planta, datastore.py, Duplicate Detection Feature, Excel Import Feature, excel_import.py (+17 more)

### Community 13 - "test_validacion.py"
Cohesion: 0.16
Nodes (21): _perfil(), test_validacion.py — validación de rangos (Nivel 1.3 del plan de mejoras).…, None representa 'sin dato' (p. ej. celda vacía en el Excel importado): no se…, Simula el caso de la importación de Excel: solo se mapean/validan los campos…, test_campo_sin_max_solo_valida_minimo(), test_parsear_clave_vacia_es_error(), test_parsear_clave_valida(), test_parsear_numerico_acepta_coma_decimal() (+13 more)

### Community 14 - "profile_builder.py"
Cohesion: 0.13
Nodes (20): build_profile_columnas(), build_profile_filas(), build_scaffold(), classify_row(), _decimal_re(), Pattern, profile_builder.py =================== Motor de detección y armado de perfiles,…, Analiza una muestra de valores crudos de un campo y sugiere {"tipo": ...,… (+12 more)

### Community 15 - "test_backups.py"
Cohesion: 0.16
Nodes (11): _crear_backup_con_fecha(), _perfil(), datetime, test_backups.py — Nivel 2.1 del plan de mejoras.…, test_purgar_elimina_tambien_el_sidecar_hash(), test_purgar_elimina_todo_lo_mas_viejo_de_un_ano(), test_purgar_mantiene_todos_los_de_hoy(), test_purgar_mantiene_uno_por_dia_dentro_de_30_dias() (+3 more)

### Community 16 - "test_io_seguro.py"
Cohesion: 0.10
Nodes (7): test_io_seguro.py — escritura atómica (Nivel 1.1 del plan de mejoras).…, newline="" (default) no debe convertir \\n sueltos a \\r\\n ni nada parecido:…, Simula un crash DESPUÉS de crear el temporal pero ANTES de completar el volcado…, Simula el escenario real observado en Windows: un antivirus/indexador tiene el…, test_fallo_a_mitad_de_escritura_no_corrompe_el_original(), test_no_traduce_fin_de_linea(), test_replace_reintenta_ante_permission_error_transitorio()

### Community 17 - "test_panel_multi_maquina.py"
Cohesion: 0.15
Nodes (13): Compila y valida el regex/plantilla de la feature 'placeholder' ACÁ, al cargar…, Coherencia de min/max/default/formato de cada campo — antes no se validaba nada…, Verifica que las filas 0..max estén todas cubiertas exactamente una vez por…, _perfil(), Tests de src/panel_multi_maquina.py (Nivel 4.9: panel multi-máquina)., Sin 'columna' fija en 'gramos' — DataStore.load() resuelve la columna por…, test_maquina_con_archivo_corrupto_reporta_error(), test_maquina_con_datos_cuenta_registros() (+5 more)

### Community 18 - "import_mapeos.py"
Cohesion: 0.14
Nodes (8): aplicar_a_headers(), cargar(), guardar(), Recordar mapeos de columnas usados en la importación (Nivel 4.6 del plan de…, {nombre_interno: texto_de_encabezado}. Vacío si nunca se guardó nada, o si el…, Traduce el mapeo guardado (nombre_interno -> texto de encabezado) a índices de…, _ruta(), Tests de src/import_mapeos.py (Nivel 4.6: recordar mapeos de columnas).

### Community 19 - "Campo"
Cohesion: 0.14
Nodes (6): BulkEditDialog, ComandoDeshacer, Aplica un mismo valor a un campo de TODOS los registros seleccionados de una…, Una acción del usuario, posiblemente compuesta por varios CambioRegistro (p.…, Campo, Clave + parámetros visibles, en el orden del perfil (para la tabla y los…

### Community 20 - "hash_archivo"
Cohesion: 0.24
Nodes (13): fue_modificado_externamente(), hash_archivo(), Detección de modificación externa (Nivel 4.3 del plan de mejoras). Aun con un…, SHA-256 del archivo, o None si no existe (todavía no se guardó nunca, o fue…, True si el contenido de `path` en disco ya no coincide con `hash_conocido` (el…, Tests de src/deteccion_externa.py (Nivel 4.3)., test_archivo_borrado_por_fuera_se_detecta(), test_archivo_cambiado_por_fuera_se_detecta() (+5 more)

### Community 21 - "Profile"
Cohesion: 0.23
Nodes (7): Pattern, La cantidad de registros a cargar se calcula recortando las celdas vacías al…, Panel multi-máquina (Nivel 4.9 del plan de mejoras). Vista consolidada, de una…, resumen_de_maquina(), resumen_de_todas(), ResumenMaquina, Profile

### Community 22 - "_center_dialog"
Cohesion: 0.26
Nodes (4): _center_dialog(), PanelMultiMaquinaDialog, Vista consolidada de todas las máquinas configuradas: una fila por máquina, de…, RecordDialog

### Community 23 - "excel_import.py"
Cohesion: 0.23
Nodes (10): abrir_archivo_importacion(), abrir_csv(), es_csv(), guess_mapping_generic(), open_workbook(), excel_import.py ================ Lectura de archivos Excel (.xlsx/.xlsm) y CSV…, Para cada campo del perfil, sugiere el índice de columna del Excel que mejor…, Abre el libro en modo solo-lectura, con fórmulas resueltas a valor. (+2 more)

### Community 24 - "_normalizar_separador_decimal"
Cohesion: 0.20
Nodes (11): _normalizar_separador_decimal(), normalize_code(), normalize_decimal(), normalize_int(), normalize_value(), Convierte el valor crudo de una celda de código a texto comparable. Excel suele…, Resuelve el caso ambiguo de un número con AMBOS separadores presentes (p. ej.…, True si `raw` (antes de redondear) representaba un número con parte… (+3 more)

### Community 25 - "HistorialDialog"
Cohesion: 0.22
Nodes (4): BackupsDialog, HistorialDialog, Lista los puntos de respaldo automáticos (backups.py) y permite restaurar uno,…, Visor de historial.jsonl: tabla filtrable por fecha, código y tipo de acción.…

### Community 26 - "test_informe.py"
Cohesion: 0.20
Nodes (4): a_filas_csv(), Informe de cambios exportable (Nivel 4.2 del plan de mejoras). A diferencia de…, Convierte una lista de eventos (como los que devuelve historial.leer_eventos())…, Tests de src/informe.py (Nivel 4.2: informe de cambios exportable).

### Community 27 - "graphify-out/graph.json"
Cohesion: 0.22
Nodes (9): graphify-out/graph.json, graphify-out/GRAPH_REPORT.md, Graphify Knowledge Graph, graphify explain command, graphify-out/ directory, graphify path command, graphify query command, graphify update command (+1 more)

### Community 28 - "log_config.py"
Cohesion: 0.33
Nodes (8): Logger, configurar_logging(), get_logger(), instalar_manejador_excepciones_no_capturadas(), log_dir(), Logging de aplicación (Nivel 3.2 del plan de mejoras). Por qué existe: si algo…, Idempotente: llamarla más de una vez no duplica handlers., Reemplaza sys.excepthook: registra la excepción en el log con traceback…

### Community 29 - "MachineSelector"
Cohesion: 0.33
Nodes (3): MachineSelector, Navegador de documentos de configuración de máquinas: lista todos los perfiles…, Construye (o reconstruye) todo el contenido del diálogo a partir de…

### Community 30 - "datastore.py"
Cohesion: 0.22
Nodes (6): _format_value(), datastore.py ============ Motor genérico de datos, guiado por un Profile…, Parsea el string crudo de una celda al valor tipado del campo (para ordenar,…, Formatea un valor tipado (editado por el usuario) al string que se escribe en…, _to_number(), ValueError

### Community 31 - "WorkbookCSV"
Cohesion: 0.25
Nodes (4): _HojaCSV, Envoltorio de una lista de filas con la misma forma que…, Envoltorio mínimo para que un .csv se pueda leer con la misma API que un…, WorkbookCSV

### Community 34 - ".iter_rows"
Cohesion: 0.40
Nodes (4): Devuelve los encabezados (fila 1) de la hoja indicada., Lee las filas de datos devolviendo, por fila, un dict {nombre_interno:…, read_headers(), read_rows_generic()

## Knowledge Gaps
- **11 isolated node(s):** `run.bat`, `profile.py`, `paths.py`, `recetas232.csv`, `Duplicate Detection Feature` (+6 more)
  These have ≤1 connection - possible missing edges or undocumented components.
- **4 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `DataStore` connect `DataStore` to `App`, `DeleteMachineDialog`, `WizardMachineDialog`, `SaludDialog`, `.from_dict`, `app.py`, `test_importacion.py`, `test_backups.py`, `Campo`, `Profile`, `_center_dialog`, `HistorialDialog`, `MachineSelector`, `datastore.py`?**
  _High betweenness centrality (0.139) - this node is a cross-community bridge._
- **Why does `Profile` connect `Profile` to `App`, `DeleteMachineDialog`, `WizardMachineDialog`, `SaludDialog`, `DataStore`, `app.py`, `.from_dict`, `profile.py`, `test_importacion.py`, `test_panel_multi_maquina.py`, `Campo`, `_center_dialog`, `HistorialDialog`, `MachineSelector`, `datastore.py`?**
  _High betweenness centrality (0.115) - this node is a cross-community bridge._
- **Why does `App` connect `App` to `SaludDialog`, `profile.py`, `WizardMachineDialog`, `DataStore`, `app.py`, `Sidecar`, `Campo`, `Profile`?**
  _High betweenness centrality (0.092) - this node is a cross-community bridge._
- **Are the 48 inferred relationships involving `DataStore` (e.g. with `App` and `BackupsDialog`) actually correct?**
  _`DataStore` has 48 INFERRED edges - model-reasoned connections that need verification._
- **Are the 5 inferred relationships involving `App` (e.g. with `DataStore` and `Sidecar`) actually correct?**
  _`App` has 5 INFERRED edges - model-reasoned connections that need verification._
- **Are the 19 inferred relationships involving `Profile` (e.g. with `App` and `BackupsDialog`) actually correct?**
  _`Profile` has 19 INFERRED edges - model-reasoned connections that need verification._
- **Are the 18 inferred relationships involving `Campo` (e.g. with `App` and `BackupsDialog`) actually correct?**
  _`Campo` has 18 INFERRED edges - model-reasoned connections that need verification._