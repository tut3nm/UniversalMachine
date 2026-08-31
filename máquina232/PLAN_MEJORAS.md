# Plan de mejoras — Configurador de Parámetros de Planta

> Documento de trabajo. Estado: **Niveles 1 a 5 implementados**. Quedan abiertos los puntos de decisión del Nivel 0.1 (repositorio) y las preguntas de la sección final.
> Última actualización: 2026-07-29

## Contexto y supuestos

Decisiones tomadas que condicionan este plan:

| Tema | Decisión |
|---|---|
| **Despliegue** | Un `.exe` portable por PC, con su carpeta `datos/` local. Un operario a la vez por máquina. |
| **Datos del repo** | Los CSV commiteados (`recetas232.csv`, `recetas232_backup_original.csv`, `record_EXPORT.csv`) **son datos reales de planta**. |
| **Trazabilidad** | Historial de cambios con capacidad de revertir. **Sin** login ni roles. |
| **Refactor** | Progresivo por fases: extraer lógica de `app.py` a medida que se toca cada área, respaldado por tests. |

Consecuencias directas:

- **No** se implementa locking de red ni merge multiusuario (Nivel 4 lo cubre solo como "instancia única" en la misma PC).
- **No** se implementa autenticación ni permisos por rol.
- **Sí** entra un nivel 0 de saneamiento del repositorio, porque hay datos reales expuestos.
- Cada nivel deja el software en un estado entregable y probado; no hay "big bang".

---

## Nivel 0 — Salvaguardas previas

**Objetivo:** no romper nada y no seguir exponiendo datos mientras se trabaja.
**Nada de esto agrega funcionalidad — es la condición para que el resto sea seguro.**
**Esfuerzo estimado: 1–2 días.**

### 0.1 · Saneamiento del repositorio Git 🔴 ✅ (parcial — ver pendiente de git history)

El repo pasó a vivir dentro del monorepo `UniversalMachine` (remoto
`github.com/tut3nm/UniversalMachine`, antes era `m-quina232` standalone).

- [x] **Decisión tomada con el usuario (2026-08-31): Opción A.** Repo privado
  + muestras anonimizadas. Confirmar la visibilidad en GitHub sigue siendo
  una acción tuya — no la puedo verificar ni cambiar yo.
- [x] Muestras anonimizadas generadas con `scripts/anonymize_csv.py`
  (mismos formatos, mismo ancho/alto de fila, códigos y valores ficticios;
  preserva la estructura de duplicados por `ignorar_ceros` y los slots
  `_DATA_N` vacíos). Validado con round-trip byte-perfecto real contra el
  motor (`DataStore.load`/`to_text()`), no sólo comparando bytes de texto.
  - `recetas232.csv` (raíz, también es el `archivo_inicial` del perfil
    232): reemplazado en el árbol de trabajo por la versión anonimizada.
  - `recetas232_backup_original.csv` y `record_EXPORT.csv`: sólo eran
    fixtures de test (ningún módulo de `src/` los usa) — movidos a
    `tests/fixtures/` en su versión anonimizada; `tests/test_engine.py`
    actualizado para apuntar ahí.
  - Los tres archivos reales originales, intactos, quedan en
    `datos_reales_privados/` (agregado a `.gitignore` — nunca se commitea).
- [ ] Evaluar si hace falta reescribir el historial de Git (`git
  filter-repo`). **Los tres CSV reales YA estaban commiteados en el
  historial previo** (commits `8c69fad`/`ebb8632`/`2aba687`, remoto viejo
  `m-quina232`) — pasar el repo a privado no borra esa exposición si
  alguna vez fue público o si hay clones/forks existentes. Reescribir
  historial invalida esos clones y requiere coordinación con quien tenga
  copias — sigue siendo una decisión y operación tuya, no la ejecuté.
- [x] Revisar que `dist/ConfiguradorPlanta.exe` no esté commiteado — sigue sin estarlo.

### 0.2 · Respaldo del estado actual de producción 🔴 ✅ hecho

- [x] Copiar la carpeta `datos/232/` completa a un respaldo fechado, fuera del repo (`respaldos_previos/datos232-<timestamp>/`, agregado a `.gitignore`), **antes de correr cualquier versión modificada de la app**.
- [x] Guardar el hash SHA-256 de `datos/232/actual.csv` y `original.csv` como referencia (`SHA256SUMS.txt` junto al respaldo).

### 0.3 · Ampliar la red de seguridad antes de refactorizar 🔴 ✅ hecho

`tests/test_engine.py` cubre bien el motor, pero el refactor progresivo del Nivel 3 necesita más superficie cubierta **antes** de mover código.

- [x] Migrar el runner casero (`check()` + lista `_fails`) a **pytest**, conservando todos los casos actuales (14 tests, todos en verde). Se agregó `requirements-dev.txt` y `tests/test_engine.py` sigue corriendo suelto (`py tests/test_engine.py`) para no romper el flujo documentado en el README.
- [x] Agregar tests de round-trip con **fixtures sintéticos** en `tests/test_synthetic.py` (no dependientes de los CSV reales), cubriendo: CRLF/LF/CR, con y sin BOM, delimitador `,` y `;`, campos ocultos, placeholders intercalados.
- [x] Test explícito de que `_raw` y `records` quedan alineados tras una secuencia larga e intercalada de `add`/`update`/`delete` (identificando los registros por código, no por índice, para que la prueba no dependa de cómo se van corriendo las posiciones).

**Hallazgo registrado durante la escritura de los tests** (no es un bug, quedó documentado en el propio test): la función `_parse_columnas` recorta las celdas vacías al **final** de la fila clave antes de contar registros — un placeholder al final del archivo no llega a contar como slot. Los slots vacíos solo "cuentan" si están intercalados entre piezas reales. Vale la pena que el Nivel 1.6 (columnas fantasma) tenga esto en cuenta.

**Criterio de salida del nivel:** repo privado o muestras anonimizadas; respaldo verificado; `pytest` verde con la cobertura actual más los casos nuevos.

---

## Nivel 1 — Integridad del dato ✅ completado

**Objetivo:** que sea imposible que un fallo (corte de luz, disco lleno, archivo corrupto) deje el archivo que va al HMI en un estado inválido, y que ningún dato inválido entre sin ser validado.
**Esfuerzo estimado: 3–5 días. Real: implementado en una sesión, 71 tests nuevos/migrados, todos en verde.**

### 1.1 · Escritura atómica 🔴 ✅

**Problema:** `DataStore.save()` ([datastore.py:283](src/datastore.py:283)) y `Sidecar.save()` ([metadata.py:41](src/metadata.py:41)) abren el archivo destino en modo `"w"`, lo que lo trunca a cero antes de escribir. Si el proceso muere en ese momento, `actual.csv` queda vacío o cortado — y es el archivo que se sube a la máquina.

**Solución:** módulo nuevo `src/io_seguro.py` con una función `escribir_atomico(path, contenido, encoding)`:

1. Escribir en `<path>.tmp` en la misma carpeta (mismo volumen, requisito para que el reemplazo sea atómico).
2. `f.flush()` + `os.fsync(f.fileno())` para forzar el volcado a disco físico.
3. `os.replace(tmp, path)` — atómico en NTFS.
4. Limpiar el `.tmp` si algo falló a mitad de camino.

- [x] Implementar `io_seguro.escribir_atomico()` + tests (incluyendo simulación de fallo entre paso 2 y 3, vía monkeypatch de `os.fsync`/`os.replace`).
- [x] Migrar `DataStore.save()` y `Sidecar.save()`.
- [x] Migrar la escritura de perfiles JSON en el wizard, y además toda copia directa que toque `actual.<ext>`/`original.<ext>` (`_seed_or_migrate`, `_migrate_legacy_232`, `on_restore`, `on_export`, alta de máquina nueva) vía un helper `copiar_atomico()` sobre `escribir_bytes_atomico()` — se encontraron varios `shutil.copyfile` más además de los ya conocidos.

### 1.2 · Autoguardado con manejo de errores y verificación 🔴 ✅

- [x] `_autosave()` ahora envuelve en `try/except OSError`, devuelve `bool`, y todos los llamadores (alta, edición, baja, duplicados, importación) solo muestran el toast de éxito si devolvió `True`.
- [x] Verificación post-escritura (`io_seguro.verificar_contenido()`, extraída como función pura y testeada aparte de la UI).
- [x] Barra de estado en rojo con "⚠ Cambios SIN guardar" ante cualquier fallo. Se agregó también `_guardar_sidecar()` con el mismo criterio para los flags de duplicados.

### 1.3 · Validación de rangos en la importación desde Excel 🔴 ✅

- [x] Extraída a `src/validacion.py` (`validar_valor_numerico`, `validar_valores_de_registro`), reutilizada tanto por `RecordDialog._on_ok` como por el diff de `ImportDialog`.
- [x] Los valores fuera de rango se marcan en rojo, con el motivo, y su casilla queda deshabilitada (`_set_all`/`_on_apply` los excluyen incluso si algo fallara en la UI — doble verificación).
- [x] Contador "N valor(es) fuera de rango — no se pueden importar" en el resumen.

### 1.4 · Corrupción del sidecar visible, no silenciosa 🟠 ✅

- [x] `Sidecar.load()` aísla el archivo corrupto a `meta.json.corrupto-<timestamp>` y expone `recuperado_de_corrupcion`/`motivo_corrupcion`/`ruta_respaldo_corrupto`; `app.py` avisa con `warn()` al activar la máquina.
- [x] Escritura atómica (cubierto por 1.1).
- **Hallazgo durante los tests:** un JSON válido pero con forma inesperada (una lista en la raíz en vez de un objeto) crasheaba con `AttributeError` sin control — no lo cubría el `except` original. Se corrigió tratándolo también como corrupción.

### 1.5 · Arranque y activación de perfil resilientes 🟠 ✅

- [x] `_activate_profile()` reescrita para no mutar `self.profile`/`self.store`/las rutas hasta que la carga nueva tuvo éxito — evita que una activación fallida deje la app con el perfil de una máquina y los datos de otra.
- [x] `_cargar_datastore_resiliente()` con diálogo de recuperación (Reintentar / Restaurar el original / Cancelar) ante cualquier archivo corrupto o desincronizado del perfil. *(La opción "restaurar desde backup" queda para el Nivel 2, que es cuando existen backups.)*
- [x] `on_restore()` con manejo de errores y copia atómica.
- **Hallazgo durante los tests (instanciando la App real):** si la activación cancelaba y destruía la ventana, `App.__init__` seguía ejecutando código sobre la ventana ya destruida (`self.bind(...)`), tirando `TclError`. Corregido con un `return` temprano.

### 1.6 · Validación de integridad al cargar el archivo 🟠 ✅

- [x] `DataStore.load()` detecta columnas fantasma (datos más allá del último registro reconocido, en campos, filas fijas o fila índice) y los expone en `store.advertencias`; `app.py` avisa con `warn()` al activar la máquina.
- [x] `to_grid()` verifica que todas las filas tengan el mismo ancho antes de escribir, y lanza `ValueError` explícito si no — nunca deja escribir un archivo con filas de ancho desigual.
- [x] Tests de regresión para ambos casos, más el caso general (sin advertencias) para no generar falsos positivos.

### 1.7 · Validación robusta del perfil JSON 🟡 ✅

- [x] El regex y la plantilla `generar` del placeholder se compilan/validan en `Profile.from_dict()` → `ProfileError` claro al cargar, no `re.error` crudo en medio del refresco de la tabla.
- [x] `_validar_campos()` nuevo: `min <= max`, `default` compatible con el tipo y dentro de rango, `formato.ancho` entero positivo para `entero_ceros`, `formato.decimales` entero ≥ 0 para `decimal`.
- [x] `'fila'` debe ser un entero real (no string, no bool) en `filas_fijas`/`fila_indice`/campos con orientación `columnas`.
- **No implementado:** la advertencia de "el patrón de placeholder podría coincidir con códigos reales" — requiere acceso a los datos cargados, no solo al perfil; quedó fuera de alcance de esta validación puramente estructural. Se puede retomar como parte del Nivel 1.6/4.5 (reporte de salud del catálogo) si se considera necesario.

**Criterio de salida del nivel — cumplido:** ningún camino de escritura puede dejar un archivo a medias (escritura atómica en todos los puntos que tocan `actual`/`original`/perfiles/sidecar); ningún valor fuera de rango entra por importación; ningún archivo corrupto (datos, metadatos o perfil) crashea la app — todos los casos ofrecen recuperación o un mensaje claro. 71 tests (24 preexistentes + 47 nuevos) en verde.

---

## Nivel 2 — Recuperabilidad e historial ✅ completado

**Objetivo:** que cualquier error humano sea reversible sin perder el trabajo posterior. Antes, la única marcha atrás era "Restaurar original", que descarta **todo**.
**Esfuerzo estimado: 5–8 días. Real: implementado en la misma sesión que el Nivel 1, 40 tests nuevos, todos en verde.**
**Decisiones ya tomadas (confirmadas con el usuario):** backups e historial viven junto al `.exe` (`datos/<id>/backups/`, `datos/<id>/historial.jsonl`), igual que el resto de los datos. Retención del historial: 1 año (se archiva comprimido, no se borra).

### 2.1 · Backups automáticos rotativos 🔴 ✅

- [x] `src/backups.py`: antes de cada guardado, copia el `actual.<ext>` vigente a `datos/<id>/backups/actual-<AAAAMMDD-HHMMSS-microsegundos>.<ext>` (microsegundos para no pisarse entre ediciones seguidas).
- [x] Política de retención implementada tal cual se planeó: todas las de hoy + una por día (30 días) + una por mes (1 año) + purga del resto. Se aplica una vez por activación de máquina.
- [x] Hash SHA-256 junto a cada backup (`.sha256`); `verificar_integridad()` lo chequea antes de ofrecer restaurar.
- [x] Diálogo **Backups** (botón en la toolbar): lista de puntos de respaldo con fecha/tamaño, marca visual si el hash no verifica, y "Restaurar este backup" con vista previa de diferencias (`resumir_diferencias`: qué se perdería / recuperaría / cambiaría).

### 2.2 · Historial de cambios 🔴 ✅

- [x] `src/historial.py`: `datos/<id>/historial.jsonl`, un evento JSON por línea, con timestamp, usuario (`getpass.getuser()`), acción, clave, valores anteriores/nuevos y origen.
- [x] Instrumentado en los puntos de mutación planeados: `on_new`, `on_edit`, `_delete_indices`, `ImportDialog` (vía `App.on_import`), `DuplicatesDialog` (vía `App.on_duplicates`), `on_restore`, restauración de backup.
- [x] Ventana **Historial**: tabla filtrable por código, acción y rango de fecha relativo (7/30/90 días); doble clic muestra el detalle completo (valores anteriores/nuevos).
- [x] Rotación por tamaño (>50 MB, `rotar_si_hace_falta`) y purga por antigüedad (>1 año, `purgar_eventos_viejos`) — ambas archivan comprimido (`.gz`), nunca borran contenido.

### 2.3 · Deshacer / Rehacer en sesión 🟠 ✅

- [x] Pila de comandos (`ComandoDeshacer` + `CambioRegistro`) que cubre alta, modificación, baja **e importación/duplicados aplicados como una sola unidad** (un solo Ctrl+Z deshace todo un lote importado, no registro por registro).
- [x] `Ctrl+Z`/`Ctrl+Y` y botones ↶/↷ en la toolbar, con estado habilitado/deshabilitado según haya algo para deshacer/rehacer.
- [x] Límite de 50 pasos (`LIMITE_DESHACER`), pila por máquina activa (se reinicia en `_activate_profile`).
- [x] "Restaurar original" y "Restaurar backup" vacían ambas pilas — no son deshacibles con Ctrl+Z.
- [x] Si el autoguardado posterior a un deshacer/rehacer falla, la operación se revierte en memoria y la pila queda como si Ctrl+Z nunca se hubiera apretado (no se puede confirmar un deshacer que no se guardó).

**Limitación conocida, documentada en el código:** deshacer una modificación que además renombró la clave no revierte el `rename_key` del sidecar (las marcas de "no es duplicado" quedan asociadas al nombre nuevo). Se consideró de alcance menor frente al costo de complejizar el comando.

### 2.4 · Revertir a un punto del historial 🟠 ✅ (con alcance ajustado)

En vez de reconstruir el catálogo campo a campo desde el log de eventos (frágil y redundante frente a lo que ya existe), la ventana de Historial tiene un botón **"Ver/restaurar backups…"** que abre el diálogo de Backups (2.1) directamente — los backups ya son una copia exacta del archivo en cada momento, más confiables que reconstruir a partir de diffs. El usuario compara visualmente la fecha del evento en el historial contra la fecha de los backups disponibles.

### 2.5 · Limpieza de metadatos huérfanos 🟡 ✅

- [x] `Sidecar.save(claves_validas=...)`: si se pasa el conjunto de claves vigentes del catálogo, descarta las marcas de claves que ya no existen (antes quedaban para siempre en `meta.json`). Sin ese argumento, el comportamiento es el de siempre (retrocompatible).
- [x] `App._guardar_sidecar()` pasa las claves vigentes en cada guardado y registra un evento `"limpieza"` en el historial cuando efectivamente se descartó algo.

**Criterio de salida del nivel — cumplido:** cualquier cambio reciente es reversible (Ctrl+Z en la sesión, o restaurando un backup — hay backups de sobra dado que se crean en cada guardado); existe un historial consultable de qué pasó, cuándo y quién estaba loggeado. 40 tests nuevos (backups, historial, deshacer/rehacer, metadatos huérfanos), suite completa en 110 tests.

**Hallazgo no trivial durante la implementación:** instanciar más de una `App` (ventana Tkinter completa) en el mismo proceso de pytest es frágil — ttkbootstrap mantiene un `Style` singleton por proceso. La solución (documentada en `tests/conftest.py`) fue relanzar cada test que instancia la App real como un subproceso de `pytest` aislado. De paso, esto expuso un problema ambiental real y no relacionado (Tcl fallando intermitentemente al leer sus propios archivos de librería bajo carga de E/S, y `os.replace()` fallando transitoriamente por `PermissionError` — este último se corrigió con un reintento breve directamente en `io_seguro.py`, una mejora real de robustez más allá de los tests).

---

## Nivel 3 — Confiabilidad del proceso ✅ completado

**Objetivo:** que las mejoras anteriores no se degraden con el tiempo y que un fallo en planta sea diagnosticable.
**Esfuerzo estimado: 5–7 días. Se puede solapar parcialmente con los niveles 1 y 2.**

### 3.1 · Refactor progresivo: extraer la lógica de negocio 🟠

`app.py` tiene 2.450 líneas mezclando interfaz, reglas de negocio y persistencia. El refactor se hace **por área, a medida que cada nivel toca esa área**, nunca de golpe:

| Extraer | Desde | Se hace en |
|---|---|---|
| `validacion.py` — validación de registros | `RecordDialog._on_ok` | Nivel 1.3 |
| `importacion.py` — cálculo de diferencias | `ImportDialog._compute_diffs` | Nivel 3.1 |
| `historial.py` — registro de eventos | (nuevo) | Nivel 2.2 |
| `io_seguro.py` — escritura atómica | `DataStore.save`, `Sidecar.save` | Nivel 1.1 |
| `arranque.py` — seed y migración legado | `App._seed_or_migrate`, `_migrate_legacy_232` | Nivel 3.1 |

- [x] Cada extracción va acompañada de sus tests **antes** de mover el código.
- [x] `importacion.py` (cálculo de diferencias, `_compute_diffs` → `calcular_diferencias`) y `arranque.py` (seed + migración legado, `_seed_or_migrate`/`_migrate_legacy_232`) extraídos, con `tests/test_importacion.py` (6 tests) y `tests/test_arranque.py` (3 tests) escritos antes de mover el código. `copiar_atomico` se movió a `io_seguro.py` (donde conceptualmente pertenece) para evitar un import circular entre `app.py` y `arranque.py`.
- [ ] Regla firme: `app.py` no debe contener ninguna decisión sobre datos que no pueda probarse sin abrir una ventana. *(Se cumple para import/arranque; `app.py` sigue teniendo 3000+ líneas — quedan más extracciones posibles para cuando el Nivel 4 vuelva a tocar esas áreas.)*

### 3.2 · Logging de aplicación 🟠 ✅

**Problema:** si en planta algo falla, no queda ningún rastro. El diagnóstico depende de que el operario recuerde qué hizo.

- [x] `src/log_config.py`: `logging.handlers.TimedRotatingFileHandler` con salida a `datos/log/app.log`, rotación diaria (sufijo `AAAAMMDD` en los archivos rotados) y retención de 30 días (`backupCount`).
- [x] Registrado: arranque y versión (`main()`), perfil activado con cantidad de registros (`_activate_profile`), cada guardado con resultado (`_autosave`, éxito y los dos casos de fallo), excepciones no capturadas con traceback completo, importaciones (ruta del Excel) y exportaciones (destino, con resultado).
- [x] Manejador global: `log_config.instalar_manejador_excepciones_no_capturadas()` reemplaza `sys.excepthook` **y** `Tk.report_callback_exception` (Tkinter no pasa los errores de callbacks de eventos por `sys.excepthook`). Un diálogo (`_mostrar_dialogo_excepcion`) muestra el error, la ruta del log y un botón "Copiar detalle" al portapapeles, en vez del traceback crudo en consola.

### 3.3 · Integración continua 🟡 ✅

- [x] `.github/workflows/tests.yml`: job `pytest` corre la suite completa en cada push y pull request sobre `windows-latest` (la plataforma real de despliegue).
- [x] Job `build-exe` (solo en tags `v*`, encadenado después de que `pytest` pase): compila con `build.bat` y publica `dist/ConfiguradorPlanta.exe` como artefacto de esa versión.
- [x] El round-trip byte-perfecto ya está cubierto por `tests/test_synthetic.py`, que corre como parte de la suite normal en cada push — no hace falta un chequeo aparte.

### 3.4 · Versionado y trazabilidad de la compilación 🟡 ✅

- [x] `src/version.py` con `APP_VERSION` y `FECHA_COMPILACION`; `build.bat` genera `src/_build_info.py` (gitignored) con la fecha real justo antes de compilar, que `version.py` importa si existe.
- [x] Versión mostrada en la barra de estado (clickeable) y en un diálogo "Acerca de" (`App.on_about`) con versión, fecha de compilación, máquina activa y ruta del log.
- [x] `historial.registrar()` acepta `version`; cada evento que pasa por `App._registrar_evento()` queda con `version=version.APP_VERSION`.
- [x] `Profile.version_esquema` (del campo `"version"` del JSON, default `1`) — no se usa aún para migrar nada, pero ya queda el campo disponible para cuando haga falta.

**Criterio de salida del nivel — cumplido:** la suite corre sola en cada push/PR (`.github/workflows/tests.yml`); cualquier fallo en planta deja evidencia en `datos/log/app.log` (con traceback, versión y contexto) suficiente para diagnosticarlo sin reproducirlo. 119 tests en verde (110 previos + 9 nuevos: 6 de `importacion.py` + 3 de `arranque.py`).

---

## Nivel 4 — Funcionalidad nueva ✅ completado

**Objetivo:** aumentar lo que el software puede hacer, sobre una base ya confiable.
**Esfuerzo estimado: 8–15 días según cuánto se incluya. Ordenado por relación valor/esfuerzo.**
**Alcance decidido con el usuario, en cuatro tandas:** 4.1/4.3/4.5, luego 4.2/4.4, luego 4.6/4.7, luego 4.8/4.9. 98 tests nuevos en total, suite completa en 217 tests.

### 4.1 · Vista de diferencias contra el original 🟠 ✅

Hoy solo se ven diferencias durante la importación de Excel. Antes de subir un archivo al HMI, el operario debería poder revisar exactamente qué cambió.

- [x] `src/diferencias.py`: `comparar_con_original(store_actual, store_original)` (función pura, sin UI) devuelve altas/bajas/modificaciones campo por campo, ignorando placeholders. `tests/test_diferencias.py` (7 tests).
- [x] Botón "🔍 Ver cambios" en la toolbar → `DiffsDialog`: tabla con checkboxes de filtro por tipo (alta/baja/modificación), doble clic para ver el detalle campo por campo de un registro.
- [x] "Exportar informe (CSV)…" respeta el filtro activo — exporta solo lo que se está viendo, no siempre todo.

### 4.2 · Informe de cambios exportable 🟠 ✅

A diferencia de 4.1 (que compara dos snapshots, `actual` vs `original`), esto exporta eventos del historial de un período — para adjuntar al parte de cambio de receta.

- [x] `src/informe.py`: `a_filas_csv(eventos)` (función pura) arma las filas del CSV a partir de eventos de `historial.leer_eventos()`. Se eligió CSV (no PDF) para no sumar una dependencia nueva solo para esto — coherente con el resto de las exportaciones de la app (4.1, "Exportar" de la barra de herramientas), todas CSV. `tests/test_informe.py` (4 tests).
- [x] Columnas: fecha, usuario, acción, código, origen, versión de la app, y valores anteriores/nuevos (como JSON compacto en una celda — son dicts de forma variable según el perfil de cada máquina, no hay columnas fijas razonables por campo).
- [x] Botón "Exportar informe (CSV)…" en `HistorialDialog`: exporta los eventos **ya filtrados** en pantalla (por código/acción/fecha), no siempre todo el historial.

### 4.3 · Detección de modificación externa 🟠 ✅

Aun con un `.exe` por PC, el archivo `actual.csv` puede ser modificado por fuera (alguien lo copia a mano, un script, la propia máquina).

- [x] `src/deteccion_externa.py`: `hash_archivo()` (SHA-256) y `fue_modificado_externamente()`. `App` guarda `self._hash_conocido` cada vez que lee o escribe `actual.<ext>` (activación, guardado, restaurar original, restaurar backup, exportar "actual"). `tests/test_deteccion_externa.py` (7 tests).
- [x] `App._resolver_modificacion_externa()`, llamado al principio de `_autosave()`: si el hash en disco no coincide con el último conocido, ofrece "Ver diferencias" (abre `DiffsDialog` contra la versión en disco, sin cerrar el diálogo de decisión), "Recargar desde disco" (descarta los cambios en memoria), "Sobrescribir con lo mío", o "Cancelar" (no guarda nada, el cambio en memoria queda intacto para reintentar). Cubierto por `tests/test_app_deteccion_externa.py` con la App real (sobrescribir/recargar/cancelar, y el caso sin conflicto que no debe preguntar nada).

### 4.4 · Instancia única 🟡 ✅

- [x] `src/instancia.py`: lock por archivo (`datos/<id>/.lock`, JSON con PID/host/timestamp). `adquirir()`/`liberar()`, con `InstanciaBloqueadaError` si el lock pertenece a un proceso vivo. `tests/test_instancia.py` (10 tests).
- [x] Limpieza de locks huérfanos: `_proceso_vivo(pid)` abre un handle de **solo consulta** vía `ctypes`/`OpenProcess` (nunca `os.kill()`, que en Windows termina el proceso en vez de solo consultarlo) — si el proceso ya no existe, el lock se toma sin más trámite.
- [x] Integrado en `App._activate_profile()`: adquiere el lock de la máquina antes de abrirla (con rollback si falla algo después); si está tomado por otro proceso vivo, avisa con el PID y no la abre. Se libera la máquina anterior al cambiar de máquina, y la propia al cerrar la ventana (`App._on_close()`, atado a `WM_DELETE_WINDOW`). Cubierto por `tests/test_app_instancia.py` con la App real (segunda ventana bloqueada, liberación al cerrar, tercera apertura exitosa).

### 4.5 · Reporte de salud del catálogo 🟠 ✅

- [x] `src/salud.py`: `evaluar_salud(store, sidecar)` junta en una sola pasada valores fuera de rango, campos obligatorios vacíos, y duplicados sin revisar (según `duplicados_config()` del perfil, reutilizando `find_similar_groups`); `contar_slots_libres()` cuenta los placeholders disponibles. `tests/test_salud.py` (7 tests).
- **No implementado:** "registros con formato sospechoso" — no hay una definición operacional de qué cuenta como "sospechoso" más allá de fuera de rango o vacío (el plan tampoco la precisa); se dejó fuera para no inventar un criterio arbitrario. Si aparece un caso concreto en planta, se agrega como un tipo de hallazgo nuevo.
- [x] Botón "❤ Salud" en la toolbar → `SaludDialog`: tabla de hallazgos con tipo/código/detalle, y "0 problemas" muestra un estado positivo explícito en vez de una lista vacía sin contexto.
- [x] Acceso directo: doble clic (o "Ir al registro") en un hallazgo llama a `App.ir_a_registro(code)`, que limpia el filtro de búsqueda, muestra placeholders si hace falta, y selecciona/enfoca la fila en la tabla principal.

### 4.6 · Mejoras en la importación 🟠 ✅

- [x] **Separador de miles:** `_normalizar_separador_decimal()` en `excel_import.py` resuelve el caso ambiguo (ambos separadores presentes: el último es el decimal, el otro es de miles y se descarta) — cubre tanto el formato regional (`1.234,56`) como el US (`1,234.56`). El caso de un solo separador se deja como estaba (decimal), porque distinguir "1.234" sin más contexto es inherentemente ambiguo.
- [x] **Aviso de redondeo:** `excel_import.tuvo_decimales(raw)` detecta si la celda original tenía parte fraccionaria; `importacion.calcular_diferencias()` lo expone como `"redondeos": [...]` en cada diff/alta, y `ImportDialog` lo muestra en ámbar ("⚠ redondeado") junto al valor, en el paso de revisión.
- [x] Importación desde **CSV**: `excel_import.WorkbookCSV` envuelve una lista de filas con la misma API que un `Workbook` de openpyxl (`sheetnames` + `iter_rows`), así que `read_headers`/`guess_mapping_generic`/`read_rows_generic` y todo `ImportDialog` funcionan sin cambios sobre CSV o Excel. `abrir_archivo_importacion(path)` elige según la extensión. De paso, `openpyxl` pasó a ser un import opcional a nivel de módulo — importar desde CSV ya no requiere tenerlo instalado.
- [x] `src/import_mapeos.py`: recuerda, por máquina, el último mapeo confirmado (guardando el TEXTO del encabezado, no el índice de columna, para que sobreviva a un archivo con las columnas en otro orden). Se aplica con prioridad sobre la sugerencia automática en el siguiente `ImportDialog`.
- [x] Vista previa: `ImportDialog._build_preview()` muestra las primeras 3 filas crudas del archivo (todas las columnas) debajo del formulario de mapeo, para confirmar a simple vista que la columna elegida es la correcta.
- Tests: `tests/test_excel_import.py` (17), `tests/test_import_mapeos.py` (6), casos de redondeo agregados a `tests/test_importacion.py`, e integración real con `ImportDialog` en `tests/test_app_importacion.py`.

### 4.7 · Búsqueda y filtros avanzados 🟡 ✅

- [x] `src/filtros.py`: `coincide_busqueda()` ahora busca en CUALQUIER campo visible del registro, no solo la clave (antes [app.py:2136] filtraba únicamente por código). `coincide_rangos()` filtra por rango numérico (min/max, cualquiera de los dos opcional) sobre los parámetros numéricos del perfil.
- [x] Botón "▾ Filtros" en la toolbar (solo si el perfil tiene algún parámetro numérico) → `FiltrosDialog`: un rango min/max por campo numérico, aplicado sobre `App._filtros_rango` (por máquina, se reinicia al cambiar de máquina como el orden de la tabla).
- [x] Filtros frecuentes: `filtros.agregar_o_reemplazar()`/`cargar_guardados()`/`eliminar()` persisten combinaciones de búsqueda + rangos por máquina (`datos/<id>/filtros_guardados.json`); el diálogo lista los guardados con "Aplicar" (rellena búsqueda + rangos y aplica de una) y "Eliminar".
- Tests: `tests/test_filtros.py` (15) más integración con la App real (búsqueda por campo no-clave, filtro de rango, guardar/reaplicar preset) en `tests/test_app_filtros.py`.

### 4.8 · Edición en línea en la tabla 🟡 ✅

- [x] `validacion.parsear_valor_campo(campo, texto)`: helper compartido (misma lógica que ya usaba `RecordDialog._on_ok`, extraída para no duplicarla) que tipa y valida rango un único valor.
- [x] Doble clic en una celda de PARÁMETRO abre un `Entry` flotante posicionado exactamente sobre la celda (vía `tree.bbox`), sin abrir `RecordDialog`. Enter/perder el foco confirma, Escape cancela. Doble clic en la celda de la CLAVE (o en modo eliminación) sigue abriendo el diálogo completo — cambiar la clave puede afectar duplicados/sidecar, no vale la pena duplicar esa lógica en la celda.
- [x] Edición masiva: botón "✎✎ Editar en masa" (habilitado con 2+ registros seleccionados, Ctrl+clic/Shift+clic) → `BulkEditDialog`: un campo + un valor, aplicado a todos los seleccionados como un solo comando deshacible (un Ctrl+Z revierte el lote completo).
- Tests: casos de `parsear_valor_campo` en `tests/test_validacion.py` (8 nuevos), integración con la App real (edición en línea + deshacer, edición masiva + deshacer) en `tests/test_app_edicion_en_linea.py`.

### 4.9 · Panel multi-máquina 🟢 ✅

- [x] `src/panel_multi_maquina.py`: `resumen_de_maquina(profile)` lee cada máquina de forma independiente y best-effort (un archivo corrupto en una no bloquea el resumen de las demás) — última modificación (mtime de `actual.<ext>`), cantidad de registros (reales, sin contar placeholders), duplicados pendientes (si el perfil tiene la feature) y cantidad de alertas de salud (reutilizando `salud.evaluar_salud`).
- [x] Botón "📊 Panel" en el header, visible solo con 3 o más máquinas configuradas (como pide el punto 2 de este ítem) → `PanelMultiMaquinaDialog`: tabla de solo lectura, filas con alerta resaltadas en ámbar y errores en rojo, doble clic para saltar a administrar esa máquina (reutiliza `App._activate_profile`, con el mismo control de instancia única del Nivel 4.4).
- Tests: `tests/test_panel_multi_maquina.py` (7) más integración con la App real (3 máquinas, resumen correcto, salto entre máquinas) en `tests/test_app_panel_multi_maquina.py`.

**Nivel 4 — completo (4.1 a 4.9).** 98 tests nuevos sobre el total del Nivel 3 (119), suite completa en 217 tests.

---

## Nivel 5 — Higiene y deuda técnica ✅ completado

**Objetivo:** limpieza de bajo riesgo. Se puede intercalar como relleno entre tareas mayores.
**Esfuerzo estimado: 1–2 días en total.**

- [x] **Código muerto en `excel_import.py`:** eliminados `ExcelRow`, `read_rows` (la variante vieja de 4 campos fijos), `guess_mapping` y `_HEADER_HINTS` — confirmado que nadie los usaba (ni en `src/` ni en `tests/`), reemplazados hace rato por las variantes `_generic`. `open_workbook` **sí** seguía vivo (lo usa `abrir_archivo_importacion`) y se mantuvo.
- [x] **Variable sin uso:** `max_col` en `read_rows_generic` ([excel_import.py](src/excel_import.py)) eliminada.
- [x] **`_strip_accents` incompleto:** reemplazado por `unicodedata.normalize('NFKD', ...)` + filtrar combining marks — ahora cubre `ü`, `à`, `ç` y cualquier diacrítico Unicode, no solo el puñado de vocales acentuadas del español. Tests agregados en `tests/test_excel_import.py`.
- [x] **`find_key` era O(n):** `DataStore` ahora mantiene un índice `clave -> posición` (`self._indice_claves`), construido bajo demanda y usado cuando `find_key()` se llama sin `exclude_index` (el camino caliente de la importación). Se invalida en `delete()` siempre, y en `update()` solo si el valor de la clave cambió — una modificación de un parámetro cualquiera no lo toca. Con claves duplicadas (posibles antes de resolverlas con el diálogo de duplicados) se preserva el mismo criterio "primera coincidencia" que tenía el recorrido lineal. 8 tests nuevos en `tests/test_datastore_indice.py`.
- [x] **Nombre inconsistente en `build.bat`:** el comentario de cabecera ahora dice `ConfiguradorPlanta.exe`, igual que el `--name` real de PyInstaller.
- [x] Consolidado en `README.md`: lista de "Qué hace la aplicación" actualizada con todo lo agregado en los Niveles 1 a 4 (deshacer/rehacer, backups, historial, salud, filtros avanzados, edición en línea, panel multi-máquina, detección de modificación externa, instancia única, importación desde CSV), y el árbol de `src/` con los ~20 módulos nuevos.

**Criterio de salida del nivel — cumplido:** sin código muerto conocido en `excel_import.py`; `find_key()` deja de ser el cuello de botella de la importación; `README.md` refleja el estado real de la app, no solo el de antes del plan. 8 tests nuevos (más las mejoras de cobertura de `_strip_accents`), suite completa en 228 tests.

---

## Resumen de secuencia recomendada

```
Nivel 0  ──►  Nivel 1  ──►  Nivel 2  ──►  Nivel 4 (completo: 4.1 a 4.9)
                  │              │
                  └──────────────┴──►  Nivel 3 (en paralelo, por área tocada)

Nivel 5: completo.
```

**Regla de oro para todo el plan:** ninguna tarea se da por terminada sin que `pytest` valide que el round-trip byte-perfecto del archivo real de la 232 sigue produciendo bytes idénticos. Es el invariante del que depende que la máquina levante el archivo.

---

## Puntos abiertos a decidir

1. **Repositorio (Nivel 0.1):** ¿alcanza con pasarlo a privado, o también anonimizamos las muestras y reescribimos el historial?
2. **Ubicación de los backups (Nivel 2.1):** ¿junto al `.exe` o en una ruta fija de la PC?
3. **Retención del historial (Nivel 2.2):** ¿un año es suficiente, o hay algún requisito de conservación de la empresa?
4. ~~**Alcance del Nivel 4**~~ — resuelto: se implementó completo (4.1 a 4.9), en cuatro tandas.
