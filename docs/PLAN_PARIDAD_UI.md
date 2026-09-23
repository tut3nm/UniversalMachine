# Plan de paridad: llevar la UI de `máquina232` (Configurador de Planta) a la webapp

> Estado: **planificación, sin implementar**.
> Fuente de verdad del comportamiento a copiar: `máquina232/src/app.py` (4.150 líneas).
> Destino: `backend/` (FastAPI) + `front/` (React + TypeScript + Vite).
> Complementa a `PLAN_WEBAPP.md` (arquitectura general); esto es el detalle de
> **paridad funcional y visual** de la interfaz.

**Decisiones tomadas con el usuario (2026-09-04)**

| Tema | Decisión |
|---|---|
| Distribución | Idéntica al escritorio: mismo orden de botones, mismos diálogos, mismos atajos |
| Colores | **No** se copia el verde hoja. Paleta nueva "azul acero" (ver 6.1) |
| Tipografía | **IBM Plex Sans**, empaquetada con la app, con cifras tabulares en la tabla |
| Deshacer y rehacer | Pila **en el backend**, por máquina, límite 50 |
| Eliminar máquina | Habilitado en la web, con confirmación por tipeo del nombre |
| Tamaño de catálogo | Más de 5000 registros: filtrado, orden y paginado **del lado del servidor** más virtualización de filas |

---

## 1. Objetivo

Reproducir en la webapp, **tal cual**, la experiencia del programa de escritorio:
el formato de la tabla, los botones y su distribución, los diálogos, los atajos
de teclado, los mensajes y las validaciones. Donde falte soporte en el backend
(endpoints, servicios) se crea. Ningún invariante del motor de datos se toca:
el round-trip byte-perfecto, el backup previo a cada guardado y el historial
auditable se conservan exactamente como están.

---

## 2. Estado actual de la webapp

| Área | Estado hoy |
|---|---|
| CRUD de registros | Implementado (`routers/maquinas.py`, `services/maquinas_service.py`) |
| Salud | Solo lista de hallazgos, sin `slots_libres` |
| Backups | Listar + restaurar (sin preview de impacto ni flag de integridad) |
| Historial | Listar (últimos 200, sin filtros) |
| Diferencias contra el original | Listar (sin exportación a CSV) |
| Wizard de alta/edición de máquina | 5 endpoints completos (`routers/wizard.py`) |
| Mediciones (IA) | Completo |
| Frontend | 5 páginas simples: Dashboard, MaquinaDetalle, Backups, Historial, Mediciones |

Lo que **no existe todavía** (ni backend ni frontend): importación desde Excel,
exportación de archivos, restaurar original, duplicados, edición en masa, modo
eliminación con multi-selección, deshacer/rehacer, filtros de rango y presets,
eliminar máquina, informes CSV, tooltips, toasts, atajos de teclado, barra de
estado, orden por columna y toggle de slots vacíos.

---

## 3. Anatomía del programa viejo (lo que hay que copiar)

### 3.1 Ventana principal (`App._build_ui`, `app.py:3366`)

Layout vertical, de arriba hacia abajo:

1. **Header** (alto fijo 64 px, fondo verde `#4E9A51`)
   - Izquierda: nombre de la máquina (Segoe UI Semibold 16) y descripción en gris claro.
   - Derecha: `🗂 Máquinas` (abre el selector) y, **solo si hay 3 o más máquinas**, `📊 Panel`.

2. **Toolbar** (fondo `#F4F6F3`, padding 16/12)
   - **Izquierda**, en este orden exacto:
     - Caja de búsqueda: ícono de lupa, input ancho 18 y texto de ayuda "Buscar por cualquier dato". Tooltip: `Ctrl+F`.
     - `▾ Filtros` (estilo *ghost*), **solo si el perfil tiene algún campo numérico visible**.
     - separador vertical
     - `＋ Nuevo` (primary), `✎ Editar` (outline), `🗑 Eliminar` (danger), `✎✎ Editar en masa` (outline, solo si hay parámetros visibles)
     - separador
     - `↶` y `↷` (ghost, pequeños; deshabilitados cuando la pila está vacía)
     - separador y `⧉ Duplicados` (secondary), **solo si el perfil declara `duplicados`**
     - separador y `📥 Importar` (secondary)
   - **Derecha**, empaquetados de derecha a izquierda, con lo que queda este orden visual: Salud, Ver cambios, Historial, Backups, Restaurar, Exportar.
     - `📤 Exportar ▾` (menú con dos ítems: archivo actual con cambios / archivo original sin cambios)
     - `⟲ Restaurar` (outline-danger)
     - `🕐 Backups`, `📜 Historial`, `🔍 Ver cambios`, `❤ Salud` (todos outline)

3. **Toggle `Mostrar slots vacíos`** (switch verde), solo si el perfil define un patrón de placeholder.

4. **Tabla** (Treeview, columnas dinámicas del perfil)
   - Primera columna `#` (ancho 60, centrada), el número de fila visible; ordenable.
   - Una columna por campo visible: título `titulo_ui`. El campo clave va a la izquierda, ancho 240, se estira; los parámetros centrados, ancho 130.
   - Alto de fila 30 px. Filas impares con fondo `#FAFBF9`. Placeholders en gris.
   - Clic en el encabezado ordena y agrega `▲` o `▼`.
   - Scroll vertical y horizontal.
   - **Doble clic** sobre una celda de parámetro abre la edición *inline* de esa celda; sobre la clave, o fuera de una celda, abre el diálogo completo.
   - `Enter` edita, `Supr` elimina la selección actual.
   - Selección múltiple (`extended`).

5. **Pie de modo eliminación** (oculto normalmente): texto "N registro(s) seleccionado(s)" y los botones `Cancelar` (outline) y `Aceptar` (danger).

6. **Barra de estado** (alto 30, fondo blanco, borde superior)
   - Izquierda: mensaje de estado ("Cambios guardados", "⚠ Cambios SIN guardar…", etc.).
   - Derecha: contador. Con placeholders muestra `N mostrados · N reales · N slots`; sin placeholders, `N mostrados · N registros`. Al lado, la versión, clickeable, que abre "Acerca de".

### 3.2 Comportamientos clave de la tabla

- **Modo eliminación** (`_enter_delete_mode`, `app.py:3826`): al tocar `🗑 Eliminar` la
  columna `#` se convierte en `☐`/`☑`, se deshabilita **toda** la toolbar, un clic en la
  fila la marca o desmarca (no selecciona), `Esc` cancela y aparece el pie de confirmación.
- **Búsqueda**: filtra por cualquier campo visible (`filtros.coincide_busqueda`), en vivo.
- **Filtros de rango**: por campo numérico, mínimo y máximo, combinables con la búsqueda.
- **Edición inline**: `Enter` guarda, `Esc` cancela, perder el foco guarda. Si el valor no
  valida se muestra una advertencia y **no** se guarda.

### 3.3 Diálogos (todos con header de color, cuerpo y footer con botones)

| Diálogo | Origen | Tamaño | Botones del footer |
|---|---|---|---|
| **MachineSelector** | `app.py:371` | auto | `➕ Agregar máquina` (izq), `🗑 Eliminar`, `Cerrar` |
| **DeleteMachineDialog** | `app.py:267` | auto, header rojo | `Confirmar eliminación`, `Cancelar` |
| **WizardMachineDialog** | `app.py:503` | 860x620 | por paso: `Atrás` (izq), `Continuar` o `Confirmar`, `Cancelar` |
| **RecordDialog** (alta/edición) | `app.py:1287` | ancho 400 a 600, alto máximo 80% de pantalla | `Guardar`, `Cancelar` |
| **DuplicatesDialog** | `app.py:1421` | 780x580 | `Eliminar seleccionados`, `Cerrar` |
| **ImportDialog** | `app.py:1558` | 720x600 | por paso: `Continuar` o `Aplicar seleccionados`, `Cancelar`/`Cerrar` |
| **BackupsDialog** | `app.py:1970` | 640x520 | `Cerrar`, y `Restaurar este backup` por fila |
| **HistorialDialog** | `app.py:2101` | 820x560 | `🕐 Ver/restaurar backups…` (izq), `Exportar informe (CSV)…`, `Ver detalle`, `Cerrar` |
| **DiffsDialog** | `app.py:2285` | 760x560 | `Exportar informe (CSV)…` (izq), `Ver detalle`, `Cerrar` |
| **SaludDialog** | `app.py:2434` | 720x520 | `Ir al registro`, `Cerrar` |
| **FiltrosDialog** | `app.py:2521` | 480x520 | `Aplicar`, `Cerrar`, más `Limpiar filtros` y `Guardar como…` |
| **BulkEditDialog** | `app.py:2673` | 420x260 | `Aplicar a N`, `Cancelar` |
| **PanelMultiMaquinaDialog** | `app.py:2773` | 760x480 | `Administrar esta máquina`, `Cerrar` |

Detalles que no se pueden perder:

- **RecordDialog**: un campo por campo visible, con etiqueta en negrita arriba y una
  ayuda a la derecha ("identificador único", "100 a 900", "número"). Usa un *spinbox* si
  el campo es entero **con mínimo y máximo**, y un input común en el resto. Valida que la
  clave no esté vacía, que los numéricos parseen, que respeten el rango, y que la clave no
  esté duplicada, avisando en qué posición ya existe. `Enter` guarda, `Esc` cancela.
- **DuplicatesDialog**: una tarjeta por grupo ("Grupo 1", "Grupo 2"…) y una fila por
  registro, con checkbox, el texto `código · Título valor · …`, y los botones `Copiar código`
  y `No es duplicado`. Marcar "no es duplicado" deshabilita la fila y la pinta en gris.
  Aplicar pide confirmación con una vista previa de hasta 6 códigos.
- **ImportDialog**: tres pasos, hoja, mapeo y diff. El mapeo carga primero el mapeo
  recordado de la última importación y por encima de él la sugerencia automática; muestra
  una vista previa de las 3 primeras filas crudas; exige la columna clave y al menos un dato
  más, y prohíbe columnas repetidas. El diff se agrupa en tres secciones, cada una con
  `Todos` y `Ninguno`: modificaciones (verde), códigos nuevos (ámbar) y códigos que no están
  en el Excel (rojo). Los ítems con error de validación llevan borde rojo y **checkbox
  deshabilitado**, y `Todos` no los marca. Los valores redondeados se marcan con "⚠ redondeado".
- **BackupsDialog**: una tarjeta por backup con fecha, tamaño en KB y, si el hash no
  verifica, "⚠ hash no verificado" y borde rojo. Antes de restaurar muestra el resumen de
  impacto: cuántos registros se perderían, cuántos se recuperarían y cuántos cambiarían.
- **HistorialDialog**: filtros por código (texto), acción (combo) y fecha (Todos, últimos
  7, 30 o 90 días), tabla de 5 columnas (Fecha, Acción, Código, Usuario, Origen), y doble
  clic para ver el detalle con el JSON de valores anteriores y nuevos.
- **DiffsDialog**: tres checkboxes de tipo (Alta, Baja, Modificación), tabla
  `Tipo | Código | Qué cambió`, colores por tipo, doble clic para el detalle campo por campo.
- **FiltrosDialog**: una fila por campo numérico (`min` a `max`), más los presets guardados
  con `Aplicar` y `Eliminar` en cada uno. `Guardar como…` pide un nombre y guarda la
  búsqueda y los rangos juntos.

### 3.4 Atajos de teclado

`Ctrl+N` nuevo, `Ctrl+F` foco en el buscador, `Ctrl+Z` deshacer, `Ctrl+Y` rehacer,
`Supr` eliminar la selección, `Enter` editar, `Esc` cerrar el diálogo o cancelar el
modo eliminación.

### 3.5 Paleta y tipografía

```
WHITE #FFFFFF   BG #F4F6F3      PANEL #FFFFFF   BORDER #D7DCD5
TEXT  #2B2F2B   MUTED #727A71
GREEN #4E9A51   GREEN_DARK #3C7A3F   GREEN_DEEP #2F5F31   GREEN_LIGHT #E7F1E3
RED   #B4472E   RED_DARK #8F3623     AMBER #C77A00
Fuente: Segoe UI 10 / bold 10 / small 9 / Semibold 16 para títulos
```

Estilos de botón (`app.py:139`): `primary` verde sólido, `danger` rojo sólido,
`secondary` gris sólido, `outline` borde verde, `ghost` tipo enlace.
Toasts en la esquina, 2,6 segundos, en verde, ámbar o rojo.

---

## 4. Matriz de paridad: qué falta

### 4.1 Backend (endpoints y servicios a crear)

| # | Función | Módulo de `core/` que la resuelve | Endpoint nuevo |
|---|---|---|---|
| B1 | Edición en masa | `datastore.update` y `validacion.parsear_valor_campo` | `POST /api/maquinas/{id}/registros/bulk-edit` |
| B2 | Baja múltiple | `datastore.delete` | `POST /api/maquinas/{id}/registros/bulk-delete` |
| B3 | Deshacer y rehacer | pila propia sobre `datastore` | `POST …/deshacer`, `POST …/rehacer`, `GET …/undo-state` |
| B4 | Duplicados | `datastore.find_similar_groups`, `metadata.Sidecar` | `GET …/duplicados`, `POST …/duplicados/no-duplicado`, `POST …/duplicados/eliminar` |
| B5 | Filtros guardados | `filtros.cargar_guardados`, `agregar_o_reemplazar`, `eliminar` | `GET`, `POST`, `DELETE` sobre `…/filtros` |
| B6 | Importar Excel o CSV | `excel_import`, `importacion`, `import_mapeos` | `POST …/import/start`, `POST …/import/mapping`, `POST …/import/apply` |
| B7 | Exportar archivo | `io_seguro.copiar_atomico` | `GET …/exportar?cual=actual|original` (descarga) |
| B8 | Restaurar el original | `io_seguro.copiar_atomico` y `DataStore.load` | `POST …/restaurar-original` |
| B9 | Informe CSV de historial | `informe.a_filas_csv` | `GET …/historial/informe.csv` |
| B10 | Informe CSV de diferencias | `diferencias.a_filas_csv` | `GET …/diferencias/informe.csv` |
| B11 | Eliminar máquina | `paths.data_dir_for` y borrado de la carpeta | `DELETE /api/maquinas/{id}` con `{ confirmacion_nombre }`, que el backend exige que coincida con el nombre de la máquina |
| B12 | Salud completa | `salud.contar_slots_libres` | ampliar `GET …/salud` |
| B13 | Backups: integridad e impacto | `backups.verificar_integridad`, `resumir_diferencias` | ampliar `GET …/backups`, nuevo `GET …/backups/{nombre}/preview` |
| B14 | Historial completo y filtrable | `historial.leer_eventos` | ampliar `GET …/historial` con `codigo`, `accion`, `desde` |
| B15 | Metadatos del perfil para la UI | `Profile` | ampliar `GET /api/maquinas/{id}` con placeholder, duplicados, extensión, orientación y campos con `min`, `max`, `formato` y `default` |
| B16 | Versión y "Acerca de" | `version`, `log_config` | `GET /api/info` |
| B17 | Advertencias de carga | `DataStore.advertencias`, `Sidecar.recuperado_de_corrupcion` | incluir en `GET …/registros` |
| B18 | Listado con búsqueda, rangos, orden y ventana | `filtros.coincide_busqueda`, `coincide_rangos` | ampliar `GET …/registros` con parámetros de consulta (ver 5.4) |
| B19 | Índices que matchean el filtro actual | `filtros.filtrar` | `GET …/registros/indices` para "seleccionar todo lo filtrado" |

### 4.2 Frontend (componentes a crear)

Sistema base: `Boton`, `Modal`, `Toast` con su proveedor, `Tooltip`, `Confirmar`,
`CampoNumerico`, `Tabla` (encabezado ordenable, filas alternadas, selección múltiple,
scroll horizontal, edición inline), `BarraEstado`, `Toolbar` y `MenuDesplegable`.

Pantallas y diálogos: `SelectorMaquinas`, `EliminarMaquina`, `Wizard` de 4 pasos,
`RegistroDialog`, `DuplicadosDialog`, `ImportarDialog`, `BackupsDialog`,
`HistorialDialog`, `DiffsDialog`, `SaludDialog`, `FiltrosDialog`, `BulkEditDialog` y
`PanelMultiMaquina`.

---

## 5. Diseño del backend

### 5.1 Regla general

Se mantiene el modelo sin estado de `maquinas_service.py`: cada request carga el
`DataStore` de disco, opera y guarda. Toda mutación pasa por un único helper que
verifica el hash esperado, crea el backup, guarda, registra en el historial y devuelve
el hash nuevo. Se generaliza `_guardar_con_backup` para aceptar **varios** cambios en
una sola operación, que es lo que hoy hace `_registrar_cambios` en la app vieja.

### 5.2 Contratos nuevos

```
POST   /api/maquinas/{id}/registros/bulk-edit
       { indices: int[], campo: str, valor: str, hash_esperado }
       -> { modificados: int, hash }

POST   /api/maquinas/{id}/registros/bulk-delete
       { indices: int[], hash_esperado } -> { eliminados: int, hash }

GET    /api/maquinas/{id}/duplicados
       -> { grupos: [{ registros: [{ index, code, valores, revisado }] }] }
POST   /api/maquinas/{id}/duplicados/no-duplicado   { code }
POST   /api/maquinas/{id}/duplicados/eliminar       { indices, hash_esperado }

GET    /api/maquinas/{id}/filtros            -> presets[]
POST   /api/maquinas/{id}/filtros            { nombre, busqueda, rangos }
DELETE /api/maquinas/{id}/filtros/{nombre}

POST   /api/maquinas/{id}/import/start       (multipart: file)
       -> { import_id, hojas[], headers[], sugerencia{}, preview[][] }
POST   /api/maquinas/{id}/import/mapping
       { import_id, hoja, mapeo }
       -> { diffs[], nuevos[], obsoletos[], sin_cambios }
POST   /api/maquinas/{id}/import/apply
       { import_id, diffs[], nuevos[], obsoletos[], hash_esperado }
       -> { hash, resumen }

GET    /api/maquinas/{id}/exportar?cual=actual|original    -> descarga
POST   /api/maquinas/{id}/restaurar-original               -> { hash }
GET    /api/maquinas/{id}/historial/informe.csv            -> descarga
GET    /api/maquinas/{id}/diferencias/informe.csv          -> descarga
DELETE /api/maquinas/{id}                                  -> { eliminada: true }
GET    /api/maquinas/{id}/backups/{nombre}/preview
       -> { integridad_ok, se_perderian[], se_recuperarian[], cambiarian[] }
GET    /api/info -> { version, compilacion, log_dir }
```

La sesión de importación se maneja igual que la del wizard (`wizard_service`): un
diccionario en memoria del proceso, con tiempo de vida y purga de sesiones viejas.

### 5.4 Listado de registros para catálogos grandes

Como el catálogo más grande de planta supera los 5000 registros, la búsqueda, los
rangos, el orden y la ventana de filas se resuelven **en el servidor**. El frontend
nunca carga el catálogo entero.

```
GET /api/maquinas/{id}/registros
    ?q=texto                     búsqueda por cualquier campo visible
    &rango=<campo>:<min>:<max>   repetible, uno por campo numérico filtrado
    &placeholders=0|1            mostrar u ocultar slots vacíos
    &orden=<campo>|pos           columna de orden
    &dir=asc|desc
    &offset=0&limit=200          ventana de filas
->  { registros[], ventana: { offset, limit },
      totales: { mostrados, reales, total },
      advertencias[], hash }

GET /api/maquinas/{id}/registros/indices?<mismos filtros>
->  { indices: int[] }           para "seleccionar todo lo filtrado"
```

`index` sigue siendo la posición real del registro en el archivo, no la posición en la
página: las mutaciones por índice (editar, borrar, edición en masa) funcionan igual con o
sin filtro aplicado. El orden y el filtro reutilizan `filtros.py` tal cual, así que la
semántica de búsqueda es idéntica a la del escritorio.

Como el archivo se relee en cada request, se agrega una caché de proceso con clave
`(ruta, mtime, tamaño)` alrededor de `DataStore.load`, para que desplazarse por la tabla
no vuelva a parsear el archivo entero en cada scroll. La caché se invalida sola cuando el
archivo cambia, incluso si lo cambió otro programa.

### 5.3 Deshacer y rehacer

La app vieja mantiene la pila **en memoria y por máquina activa**, con límite 50, y la
vacía al restaurar un backup o el original. En la webapp la pila vive en el proceso del
backend, en un diccionario de máquina a par de pilas, con la misma semántica: se apila
**después** de que el guardado confirmó éxito, un comando puede agrupar varios cambios
(una importación entera se deshace de una sola vez), y al deshacer se registra el evento
inverso en el historial con origen "deshacer". Se vacía ante una restauración de backup
o del original, y ante un conflicto de hash.

---

## 6. Diseño del frontend

### 6.1 Tokens: paleta "azul acero" y tipografía

La distribución se copia del escritorio, pero **no la paleta**. Se reemplazan los tokens
de `App.css` por estos, conservando el tamaño generoso de controles pensado para planta.
Sin degradés, sin transiciones largas, con foco siempre visible.

```css
:root {
  --bg:            #F5F7FA;   /* fondo de la app          (era #F4F6F3) */
  --surface:       #FFFFFF;   /* paneles, tarjetas, tabla */
  --border:        #D8DEE6;
  --border-strong: #B7C1CD;

  --text:          #15202B;
  --muted:         #5A6B7C;

  --primary:       #1D4E7C;   /* acción principal, header  (era #4E9A51) */
  --primary-dark:  #143A5D;   /* hover, títulos            (era #3C7A3F) */
  --primary-soft:  #E4EDF5;   /* fondo de fila activa/hover(era #E7F1E3) */
  --on-primary:    #FFFFFF;

  --success:       #2E7D4F;
  --danger:        #B3261E;
  --danger-dark:   #8C1D17;
  --warning:       #B26A00;

  --row-alt:       #FAFBFC;   /* fila impar de la tabla    (era #FAFBF9) */
}
```

Correspondencia con el escritorio, para no perder ningún significado de color: el verde
de acción pasa a `--primary`, el verde oscuro de títulos a `--primary-dark`, el verde
claro de hover a `--primary-soft`, el rojo de acciones destructivas a `--danger`, el
ámbar de advertencias a `--warning`. El verde queda reservado únicamente para
confirmaciones de éxito (`--success`), de modo que "guardado bien" y "acción principal"
dejan de ser el mismo color, cosa que en el escritorio se confundía.

**Tipografía: IBM Plex Sans**, en pesos 400, 500 y 600, con **IBM Plex Mono** solo para
la vista previa del archivo crudo en el wizard (donde hoy se usa Consolas). Los archivos
`.woff2` se guardan en `front/public/fonts/` y se declaran con `@font-face`, sin CDN: la
app corre empaquetada en una PC de planta que puede no tener internet.

```css
--font-ui:   "IBM Plex Sans", "Segoe UI", system-ui, sans-serif;
--font-mono: "IBM Plex Mono", Consolas, monospace;
```

Toda celda numérica y toda columna de códigos lleva `font-variant-numeric: tabular-nums`,
para que los dígitos queden alineados en columna. Tamaño base 16 px en la tabla y 15 px
en textos de ayuda, con alto de fila de 34 px, algo mayor que los 30 px del escritorio,
porque en navegador el clic suele ser menos preciso.

### 6.2 Estructura de la pantalla de máquina

`MaquinaDetalle` pasa a ser el equivalente exacto de la ventana principal: header verde
con el nombre y los botones de máquinas y panel, toolbar con el mismo orden de botones,
toggle de slots, tabla y barra de estado fija abajo. Los diálogos son **modales sobre la
misma pantalla**, no rutas separadas, igual que en el escritorio. Las rutas actuales de
backups e historial se conservan como enlaces profundos que abren el modal correspondiente.

### 6.3 Tabla

Sin paginación visible, porque el escritorio no la tiene: se ve una sola lista continua
que se desplaza. Por debajo, la tabla es **virtualizada** y pide al servidor ventanas de
200 filas a medida que el usuario baja (endpoint de 5.4), con un margen por delante y por
detrás para que el scroll no muestre huecos.

El resto es igual al escritorio: orden por columna con flecha, filas alternadas,
placeholders en gris, selección múltiple con `Ctrl` y `Shift`, edición inline en celdas de
parámetro, y doble clic en la clave que abre el diálogo completo.

Dos ajustes que impone el tamaño del catálogo:

- La búsqueda se dispara con un retardo corto tras dejar de tipear, no en cada tecla.
- La selección se guarda como conjunto de índices, no de filas renderizadas, para que
  sobreviva al scroll. El modo eliminación agrega "Seleccionar todo lo filtrado", que usa
  el endpoint de índices y evita tener que bajar 5000 filas a mano.

### 6.4 Estado y concurrencia

El hash que devuelve cada lectura y cada mutación se guarda en el estado de la pantalla
y se reenvía en la mutación siguiente. Un `409` abre el diálogo de conflicto con las tres
opciones del escritorio: ver diferencias, recargar desde disco, o sobrescribir con lo
propio.

---

## 7. Fases

| Fase | Contenido | Verificación |
|---|---|---|
| **F1, base visual** ✅ | Tokens, `Boton`, `Modal`, `Toast`, `Tooltip`, `Confirmar`, `BarraEstado`, layout de la pantalla de máquina, atajos de teclado | Comparación visual contra el escritorio |
| **F2, tabla completa** ✅ | Listado con filtros y orden en el servidor y caché por mtime (B18, B19), tabla virtualizada, orden, búsqueda, toggle de slots, selección múltiple, modo eliminación, edición inline, contadores | Tests de los parámetros de consulta y prueba de carga con un catálogo sintético de 10 000 registros |
| **F3, CRUD y diálogos simples** ✅ | `RegistroDialog`, `BulkEditDialog`, `SaludDialog` con slots libres, `FiltrosDialog`, más B1, B2, B5 y B12 | Tests de los endpoints nuevos en `backend/tests/` |
| **F4, historia y archivos** ✅ | `BackupsDialog` con preview, `HistorialDialog` con filtros y detalle, `DiffsDialog`, informes CSV, exportar y restaurar original: B7 a B10, B13 y B14 | Tests de endpoints y descarga real |
| **F5, importación y duplicados** ✅ | `ImportarDialog` de 3 pasos y `DuplicadosDialog`: B4 y B6 | Tests con los archivos de `docs/` y `datos_reales_privados/` |
| **F6, deshacer y multi-máquina** ✅ | Pila de comandos (B3), `SelectorMaquinas`, `EliminarMaquina` (B11), `PanelMultiMaquina`, wizard de 4 pasos sobre los endpoints ya existentes | Tests de integración de la semántica de deshacer |

Cada fase termina con `pytest` en verde en `backend/tests/` y con `npm run build` y
`npm run lint` limpios en `front/`.

### 7.1 Fase 1 — entregado (2026-09-04)

**Estilos** — `front/src/styles/tokens.css` (paleta azul acero y tipografía),
`base.css` (reset, controles, clases genéricas de las páginas) y `ui.css`
(componentes y armazón de la pantalla de máquina). Se eliminó `App.css`. La
tipografía se sirve desde el propio build: se agregaron `@fontsource/ibm-plex-sans`
y `@fontsource/ibm-plex-mono` y se quitó el enlace a Google Fonts de `index.html`,
que era una dependencia de internet que en planta no se puede dar por hecha.

**Componentes** — `front/src/ui/`: `Boton` (siete estilos, tamaño chico, tooltip
integrado), `Modal` (franja de color, cuerpo con scroll, footer, cierre con `Esc`,
foco al primer control y restitución del foco al cerrar), `Tooltip` (funciona
también sobre botones deshabilitados y se corre solo si toca un borde de la
ventana), `ToastProvider` con `useToast`, `DialogoProvider` con `useDialogos`
(`confirmar` y `avisar` como promesas, con la opción de exigir que se tipee un
texto para confirmar, pensada para el borrado de una máquina), `MenuDesplegable`,
`Separador` y `BarraEstado`.

**Atajos** — `front/src/hooks/useAtajos.ts`, con la tabla de 3.4. Las teclas
sueltas se ignoran mientras el foco está en un campo de texto; las combinaciones
con `Ctrl` funcionan siempre.

**Pantalla de máquina** — `front/src/pages/MaquinaDetalle.tsx` reescrita con las
tres franjas del escritorio y el orden exacto de botones de 3.1. Los botones cuya
función llega en fases posteriores se muestran deshabilitados, con el tooltip
original del escritorio más la aclaración de que todavía no está disponible.

**Backend** — `GET /api/info` para la barra de estado y el "Acerca de", y
`GET /api/maquinas/{id}` ampliado (B15) con `extension`, `orientacion`,
`archivo_inicial`, `tiene_placeholders` y `tiene_duplicados`, que es lo que decide
qué botones existen en la toolbar. Tests nuevos en `backend/tests/test_api_info.py`.

**Dos cosas que se adelantaron de fases posteriores**, porque sin ellas la pantalla
quedaba peor que la que ya existía:

1. `RegistroDialog` (estaba en F3): alta y edición con etiqueta, ayuda por campo y
   spinbox para enteros con rango. F3 le agrega el aviso de código duplicado que ya
   devuelve el backend.
2. Modo eliminación con casillas (estaba en F2): la toolbar se bloquea, la columna
   `#` pasa a `☐`/`☑` y aparece el pie de confirmación. Por ahora la baja múltiple
   se hace en varios requests, de mayor a menor índice; F3 la reemplaza por el
   endpoint atómico B2.

**Verificación** — 203 tests del backend en verde, `npm run build` y `npm run lint`
limpios, y prueba manual contra la máquina 232 real (673 registros): tabla, orden,
selección, modo eliminación, diálogo de alta, diálogo de aviso y tooltips.

### 7.2 Fase 2 — entregado (2026-09-04)

**Backend** — `GET /api/maquinas/{id}/registros` pasó a resolver todo del lado del
servidor: búsqueda libre, rangos numéricos repetibles (`rango=campo:min:max`), toggle
de slots vacíos, orden por columna y ventana (`offset`/`limit`, tope de 1000). La
respuesta trae la ventana, los totales del conjunto entero, las advertencias de carga
(B17) y el hash. Cada registro incluye `index`, su posición real en el archivo, y
`pos`, su lugar en la lista filtrada. Se agregó
`GET /api/maquinas/{id}/registros/indices` (B19), que devuelve todos los índices que
matchean el filtro, para "seleccionar todo lo filtrado".

El criterio de filtrado y orden reusa `filtros.py` y replica `App._visible_rows` y
`refresh_table` del escritorio: numérico real en campos numéricos con los vacíos al
final, alfabético sin distinguir mayúsculas en el resto. Un rango sobre un campo que
no es numérico, o una columna de orden inexistente, devuelven 422.

**Caché de lectura** — `_cargar_store_cacheado` guarda el último `DataStore` por
archivo, con clave de fecha de modificación y tamaño. Sin esto, cada scroll volvía a
parsear el CSV entero. Las rutas que mutan siguen cargando su propia copia con
`_cargar_store`: compartir el objeto con la caché haría que un alta se viera en las
lecturas antes de guardarse. La caché se invalida sola cuando el archivo cambia,
incluso si lo cambió otro programa.

**Tabla virtualizada** — `front/src/components/TablaRegistros.tsx` renderiza solo las
filas a la vista más ocho de margen arriba y abajo, y reserva el alto del resto con
dos filas espaciadoras, de modo que el scroll representa el catálogo entero. La tabla
usa `table-layout: fixed`: con ancho automático, cada ventana de filas recalcularía el
ancho de las columnas según su propio contenido y las columnas bailarían al scrollear.

**Catálogo por ventanas** — `front/src/hooks/useCatalogo.ts` mantiene las filas ya
traídas indexadas por posición y pide páginas de 200 a medida que la tabla las
necesita. Al cambiar el filtro o el orden se descarta lo cargado, porque las
posiciones pasan a significar otra cosa, y la tabla se remonta para volver arriba.

**Interacción** — búsqueda con espera de 250 ms antes de consultar; orden por
encabezado con flecha; selección múltiple con Ctrl y con Shift, donde el rango se pide
al servidor porque puede abarcar filas que la tabla todavía no bajó; modo eliminación
con "Seleccionar todo lo filtrado"; y edición en línea de una celda de parámetro con
Enter para guardar, Escape para cancelar y guardado al perder el foco, validando
antes de mandar con la misma lógica que el escritorio (`front/src/validacion.ts`).

**Verificación** — 228 tests del backend en verde, 25 de ellos nuevos en
`backend/tests/test_api_registros.py`, incluida una prueba de carga que recorre un
catálogo sintético de 10 000 registros en ventanas de 200 y verifica que el archivo se
lee **una sola vez**. Prueba manual sobre ese mismo catálogo: alto de fila exacto,
altura de scroll de 340 034 px con 30 filas en el DOM, carga correcta de una ventana
lejana, búsqueda que baja a 42 resultados volviendo arriba, orden por columna,
selección de los 42 filtrados y edición en línea persistida.

### 7.3 Fase 3 — entregado (2026-09-04)

**Chequeo de clave duplicada (gap encontrado al portar `RecordDialog`)** — el
escritorio nunca deja crear ni editar un registro con una clave que ya existe
(`RecordDialog._on_ok`, máquina232/src/app.py:1377), pero la webapp de las fases 1 y 2
no reproducía ese chequeo: `DataStore.add`/`update` confían en que el llamador ya lo
validó. Se agregó `ClaveDuplicada` en `maquinas_service.py`, con el mismo mensaje del
escritorio ("Ya existe un registro con «X» (posición N)"), verificado ANTES de tocar
el store (así no hay nada que revertir si falla) y mapeado a 409 en los routers de
alta y edición.

**Guardado agrupado (B1/B2)** — `_guardar_con_backup` se generalizó para aceptar una
lista de `CambioRegistro`: un solo backup y un solo `store.save()` por operación, pero
un evento de historial por registro — la misma relación que `_registrar_cambios` en
el escritorio (máquina232/src/app.py:3051), donde una importación entera es "un
comando" pero cada alta/baja/modificación queda trazada por separado.

- `POST /api/maquinas/{id}/registros/bulk-edit`: valida el campo (rechaza la clave y
  cualquier nombre que no sea un parámetro visible) y el valor con
  `validacion.parsear_valor_campo` — la misma función que usa la edición individual y
  la edición en línea — antes de tocar cualquier registro.
- `POST /api/maquinas/{id}/registros/bulk-delete`: reemplazó el bucle de N requests
  secuenciales que tenía el frontend desde la fase 2 por una sola llamada atómica.
  Índices repetidos en la selección del cliente se deduplican solos.

**Salud completa (B12)** — `GET /api/maquinas/{id}/salud` ahora usa la caché de
lectura (es una consulta, no una mutación) y agrega `slots_libres` junto a los
hallazgos, con `salud.contar_slots_libres`.

**Filtros guardados (B5)** — `GET`/`POST`/`DELETE /api/maquinas/{id}/filtros`
envuelven `filtros.py` tal cual, reusando el mismo formato `"campo:min:max"` que ya
usa el listado de registros — un preset guardado y un filtro aplicado en la URL son
la misma representación en todo el sistema.

**Frontend** — `RegistroDialog` cambió de `onGuardar: (v) => void` a
`onGuardar: (v) => Promise<string | void>`: un error (clave duplicada, valor fuera de
rango, conflicto de guardado) se muestra en el mismo recuadro rojo del diálogo sin
cerrarlo ni perder lo tipeado, en vez de saltar a un aviso aparte y descartar el
formulario. `BulkEditDialog` sigue el mismo patrón. Se agregaron `SaludDialog` (con
"Ir al registro", que en la tabla virtualizada es poner el código en la búsqueda, no
un scroll físico) y `FiltrosDialog` (filas de rango, Limpiar que aplica sin cerrar,
Guardar como… y la lista de presets con Aplicar/Eliminar). Los tres botones que
estaban deshabilitados desde la fase 1 (`✎✎ Editar en masa`, `▾ Filtros`, `❤ Salud`)
quedaron activos.

**Verificación** — 249 tests del backend en verde, 21 nuevos en
`backend/tests/test_api_masivo.py` (clave duplicada en alta/edición, edición y baja en
masa con validación previa a mutar nada, salud con slots libres, filtros guardados).
Prueba manual sobre una máquina sintética con un valor fuera de rango y un campo
vacío a propósito: el panel de salud los listó correctamente, "Ir al registro" achicó
la tabla al código exacto, un filtro de rango guardado como preset se reaplicó
trayendo de vuelta la búsqueda y los límites numéricos juntos, la edición en masa
sobre 3 registros seleccionados con Ctrl+clic pidió confirmación con el texto exacto
del escritorio y los movió fuera del rango filtrado (verificado también por API), y
el alta con una clave repetida mostró el error dentro del diálogo sin cerrarlo.

### 7.4 Fase 4 — entregado (2026-09-17)

**Backend** (`backend/app/services/consulta_service.py`, ampliado; sin nada
nuevo en `core/`, todo lo que hacía falta ya existía: `backups.py`,
`historial.py`, `diferencias.py`, `informe.py`, `io_seguro.py`):

- `GET /api/maquinas/{id}/backups/{nombre}/preview` (B13): resume el
  impacto de restaurar un backup — qué códigos se perderían, cuáles se
  recuperarían y cuáles cambiarían de valor (`backups.resumir_diferencias`),
  más `integridad_ok`. `GET .../backups` también trae `integridad_ok` por
  fila.
- `POST /api/maquinas/{id}/backups/{nombre}/restaurar`: dejó de bloquear
  por hash no verificado. El escritorio (`BackupsDialog._on_restaurar`,
  app.py:2044) solo ADVIERTE si el hash no verifica y deja decidir al
  operario después de ver el resumen de impacto — bloquear en el backend
  contradecía eso.
- `POST /api/maquinas/{id}/restaurar-original` (B8): respalda el estado
  vigente, copia `original.<ext>` sobre `actual.<ext>` de forma atómica y
  registra `"restauracion"` con clave `"original"`.
- `GET /api/maquinas/{id}/historial` ahora acepta `codigo`, `accion` y
  `desde` (días) (B14). El filtro (`consulta_service._eventos_filtrados`)
  replica `HistorialDialog._eventos_filtrados` del escritorio: substring
  sin distinguir mayúsculas en el código, acción exacta, antigüedad en
  días — no existía en `historial.py` porque allá vivía en la UI.
- `GET /api/maquinas/{id}/historial/informe.csv` (B9) y
  `GET /api/maquinas/{id}/diferencias/informe.csv` (B10): CSV armado en
  memoria (`io.StringIO` + BOM utf-8-sig, igual que el escritorio) y
  servido por `StreamingResponse` con `Content-Disposition: attachment` —
  no hace falta archivo temporal en disco. El informe de historial exporta
  TODO lo que matchea el filtro, sin el tope de `limite` de la vista
  (igual que el escritorio exporta lo mostrado en su tabla sin paginar). El
  de diferencias exporta solo los tipos que quedan marcados en los
  checkboxes, igual que `DiffsDialog._exportar` (app.py:2406).
- `GET /api/maquinas/{id}/exportar?cual=actual|original` (B7): `FileResponse`
  directo sobre el archivo en disco.

**Frontend** — tres diálogos nuevos en `front/src/dialogs/`:

- `BackupsDialog`: antes de restaurar pide el preview al backend y arma el
  mismo mensaje del escritorio ("N registro(s) que hoy existen se
  PERDERÍAN", "…se RECUPERARÍAN", "…CAMBIARÍAN de valor", con hasta 6
  códigos de muestra), agrega la advertencia de hash no verificado si
  corresponde, y pide confirmación con `useDialogos` antes de restaurar.
- `HistorialDialog`: filtros de código/acción/fecha, tabla de 5 columnas,
  clic para seleccionar una fila y "Ver detalle" (o doble clic) muestra el
  JSON de antes/después, acceso directo a Backups desde el footer, y
  exportar abre el CSV en una pestaña nueva.
- `DiffsDialog`: checkboxes de Alta/Baja/Modificación con contador cada
  uno, tabla con "qué cambió" resuelto a `titulo_ui`, detalle campo por
  campo, y exportar solo lo que dejan ver los checkboxes activos.

`MaquinaDetalle.tsx` perdió los últimos botones deshabilitados de la
toolbar: `🔍 Ver cambios`, `📜 Historial`, `🕐 Backups`, `⟲ Restaurar` y
`📤 Exportar ▾` abren ahora los diálogos de verdad (o, para exportar,
`window.open` a la URL de descarga). Las rutas viejas
`/maquinas/:id/backups` y `/maquinas/:id/historial` (`pages/Backups.tsx`,
`pages/Historial.tsx`) pasaron a ser redirecciones con
`<Navigate state={{abrir: ...}}>` a `/maquinas/:id`, que abre el modal
correspondiente al montar — los enlaces profundos siguen funcionando pero
ya no duplican la UI, como pide 6.2 del plan.

**Verificación** — 268 tests del backend en verde, 19 nuevos en
`backend/tests/test_api_historia_archivos.py` (preview de impacto,
restaurar sin bloquear por hash, restaurar original, historial filtrado
por código/acción/antigüedad, informes CSV con y sin filtro, exportar
actual/original). `npm run build` y `npm run lint` limpios. Prueba manual
contra la máquina 232 real (673 registros, servida por el backend real en
`:8000`): edición de un registro por API, Historial mostrando el evento
con su detalle JSON correcto, Backups mostrando el preview de impacto
("1 registro(s) CAMBIARÍAN de valor") y restaurando correctamente, Ver
cambios comparando contra el original, Restaurar (⟲) con su confirmación,
y los tres endpoints de descarga (`exportar`, `historial/informe.csv`,
`diferencias/informe.csv`) devolviendo `Content-Disposition: attachment`
con el contenido esperado.

### 7.5 Fase 5 — entregado (2026-09-17)

**Backend** — nada faltaba en `core/` (`excel_import.py`, `importacion.py`,
`import_mapeos.py`, `datastore.find_similar_groups`, `metadata.Sidecar` ya
estaban del trabajo previo del escritorio); todo el trabajo fue de
orquestación:

- `backend/app/services/duplicados_service.py` (B4): `listar_duplicados`
  agrupa con `find_similar_groups`, excluyendo lo que el sidecar ya marcó
  `no_duplicado` — igual que `DuplicatesDialog.__init__` (app.py:1421).
  `marcar_no_duplicado` persiste el flag y devuelve la lista actualizada.
  `eliminar_duplicados` reutiliza `eliminar_en_masa` de la Fase 3 tal cual
  (misma semántica: un backup, un evento de historial por registro).
- `backend/app/services/import_service.py` (B6): sesión en memoria con TTL
  de 30 minutos, mismo patrón que `wizard_service.py` (dict global keyed
  por `import_id`, purga por antigüedad). Cuatro pasos: `iniciar` (sube el
  archivo, abre la primera hoja), `elegir_hoja` (solo hace falta si el
  archivo tiene más de una), `mapear` (con las mismas tres validaciones del
  escritorio: clave obligatoria, al menos un dato más, sin columnas
  repetidas — `ImportDialog._on_mapping`, app.py:1697 — y guarda el mapeo
  confirmado con `import_mapeos.guardar` para la próxima vez) y `aplicar`
  (ediciones en el lugar, luego altas, luego bajas en orden descendente de
  índice — mismo orden que `ImportDialog._on_apply`, app.py:1929 — para que
  ninguna mutación corra los índices que ya calculó el paso de mapeo).
- `_guardar_con_backup` (en `maquinas_service.py`) ganó un parámetro
  `origen` opcional (por defecto `"webapp"`, sin tocar ningún llamador
  existente): la importación pasa `origen="importacion"`, así el historial
  distingue qué cambios vinieron de una importación de los editados a
  mano, sin inventar un evento "resumen" que rompería el invariante de "un
  evento por registro" (sección 8, invariante 3).
- Endpoints nuevos: `GET/POST .../duplicados`, `.../duplicados/no-duplicado`,
  `.../duplicados/eliminar`, y `POST .../import/{start,hoja,mapping,apply}`
  (rutas `backend/app/routers/duplicados.py` y `importacion.py`, registradas
  en `main.py`).

**Frontend** — dos diálogos nuevos en `front/src/dialogs/`:

- `DuplicadosDialog`: una tarjeta por grupo con "Copiar código"
  (`navigator.clipboard`) y "No es duplicado" (deshabilita la fila al
  instante y no vuelve a aparecer tras recargar), selección múltiple y
  "Eliminar seleccionados" con preview de hasta 6 códigos antes de
  confirmar — igual que el escritorio.
- `ImportarDialog`: selector de archivo nativo del navegador (reemplaza el
  explorador de Windows, según el supuesto 9.1 del plan) → paso de hoja
  (solo si el archivo tiene varias) → mapeo de columnas con vista previa de
  las primeras filas → revisión en tres secciones (Modificaciones, Códigos
  nuevos, Obsoletos) con "Todos"/"Ninguno" por sección, que no marca los
  ítems con error de validación, y aviso de "⚠ redondeado" cuando el Excel
  traía decimales para un campo entero.

Los botones `⧉ Duplicados` y `📥 Importar` de la toolbar, deshabilitados
desde la Fase 1, quedaron activos.

**Verificación** — 285 tests del backend en verde, 17 nuevos en
`backend/tests/test_api_importacion.py` (agrupamiento de duplicados,
persistencia de "no es duplicado", borrado con evento de historial,
inicio de importación CSV con sugerencia automática, las tres validaciones
del paso de mapeo, cálculo de diffs/nuevos/obsoletos, detección de valores
fuera de rango, aplicar con un solo backup y un evento por registro,
aplicar parcial, conflicto de hash, cierre de la sesión tras aplicar, y
persistencia del mapeo recordado entre dos importaciones). `npm run build`
y `npm run lint` limpios. Prueba manual contra la máquina 232 real (673
registros, 52 duplicados reales detectados de fábrica): el diálogo de
Duplicados agrupó y mostró los 25 grupos correctamente, "No es duplicado"
persistió en `meta.json` y ocultó la fila; para Importar (el input de
archivo nativo no se puede automatizar en el navegador embebido de este
entorno) se verificó el flujo completo por API contra los datos reales —
inicio con sugerencia automática de columnas, cálculo de diffs con más de
300 obsoletos correctamente detectados, aplicar una modificación y un alta
seleccionados (sin tocar los obsoletos), y confirmación de que el
historial quedó con `origen: "importacion"` — y se restauró el archivo
original al terminar.

### 7.6 Fase 6 — entregado (2026-09-17)

Última fase del plan: con esto queda cerrada la paridad funcional completa
de `máquina232/src/app.py` en la webapp.

**Deshacer y rehacer (B3)** — `backend/app/services/maquinas_service.py`:
pilas de deshacer/rehacer en memoria del proceso, una por máquina
(`_PILAS_DESHACER`/`_PILAS_REHACER`, sin TTL — viven mientras el backend
esté arriba), límite de 50 comandos como el escritorio
(`ComandoDeshacer`, `LIMITE_DESHACER`, app.py:65). `_guardar_con_backup`
ganó un parámetro `descripcion` opcional: cuando viene, apila `cambios`
como un comando deshacible — así `crear_registro`, `actualizar_registro`,
`eliminar_registro`, `editar_en_masa`, `eliminar_en_masa` e
`import_service.aplicar` quedan cubiertos con un cambio mínimo en cada
llamador (una línea con la descripción), sin duplicar lógica. Al deshacer
se calcula el INVERSO real de cada cambio (una alta se deshace con una
baja, no con un evento con el mismo `accion` y los campos cruzados como
hace literalmente el escritorio en app.py:3120 — acá se prefirió la
semántica correcta del historial sobre la réplica textual de ese detalle,
que no cambia nada visible para el operario). `marcar_no_duplicado` NO
empuja a la pila (solo toca el sidecar de metadatos, el
escritorio tampoco lo trata como deshacible). Restaurar un backup, el
original, o eliminar la máquina vacían ambas pilas (`limpiar_pilas_deshacer`),
igual que el escritorio deshabilita los botones tras una restauración
(app.py:3836).

Endpoints nuevos en `backend/app/routers/consulta.py`: `GET
.../undo-state`, `POST .../deshacer`, `POST .../rehacer`.

**Eliminar máquina (B11)** — `maquinas_service.eliminar_maquina` borra el
perfil y la carpeta `datos/<id>/` completa (`shutil.rmtree`), igual que
`DeleteMachineDialog._delete_profile_and_data` (app.py:352), pero con la
confirmación por tipeo del nombre exigida **también del lado del
servidor** (`ConfirmacionInvalida` si no coincide exactamente con
`profile.nombre`) — nunca alcanza con que el frontend ya la haya pedido.
Nuevo `DELETE /api/maquinas/{id}` con `{ confirmacion_nombre }`.

**Frontend** — dos piezas nuevas:

- `SelectorMaquinasDialog`: copia `MachineSelector` del escritorio
  (app.py:371) — una tarjeta por máquina, la actual marcada, `➕ Agregar
  máquina` abre el wizard, `🗑 Eliminar` pide confirmación con
  `exigirTexto: nombre` (el mismo mecanismo de tipeo que ya existía en
  `DialogoProvider` desde fases anteriores, sin tocarlo). El botón `🗂
  Máquinas` de la toolbar, que hasta ahora navegaba al Dashboard, abre
  este modal — el Dashboard queda como el panel multi-máquina puro
  (supuesto 9.1: ya tenía las columnas necesarias, solo le faltaba el
  botón `➕ Nueva máquina`).
- `WizardMaquinaDialog`: los 4 pasos del escritorio (archivo/identidad →
  orientación → campos → validación byte-perfecta y confirmar) sobre los
  5 endpoints de `/api/wizard/*` que ya existían enteros del trabajo de
  escritorio — esta fase era pura UI, nada de backend nuevo para el
  wizard. El paso de campos deja elegir la clave (radio), incluir/excluir
  cada fila/columna, su nombre interno, título, tipo y rango, con la
  muestra de valores reales al lado para reconocer el dato. El paso final
  llama a validar automáticamente al entrar y solo habilita "Confirmar"
  si el resultado fue byte-perfecto.

Los botones `↶`/`↷` de la toolbar, deshabilitados desde la Fase 1, quedan
activos con `Ctrl+Z`/`Ctrl+Y` y tooltip con la descripción del comando
("Deshacer: Editar «C001»").

**Verificación** — 305 tests del backend en verde, 20 nuevos en
`backend/tests/test_api_deshacer_y_maquina.py` (deshacer/rehacer de alta,
edición y baja individuales, de una edición en masa y de una importación
completa como una sola unidad, historial con `origen: "deshacer"/"rehacer"`,
límite de 50 comandos, vaciado de las pilas al restaurar backup u
original, `marcar_no_duplicado` sin efecto en la pila, y eliminar máquina
con nombre correcto/incorrecto/inexistente). `npm run build` y `npm run
lint` limpios. Prueba manual end-to-end contra el backend real: se creó
una máquina de prueba completa con el wizard (subida de CSV real,
clasificación automática de columnas, validación byte-perfecta ok,
confirmación), se editó un valor y se deshizo y rehizo desde los botones
de la toolbar en el navegador (verificado visualmente que el valor
cambiaba de 777 a 555 y volvía), se abrió el selector de máquinas
mostrando ambas máquinas con la actual marcada, y se eliminó la máquina de
prueba con la confirmación por tipeo del nombre completo — confirmado por
API que el perfil y la carpeta de datos desaparecieron del disco por
completo.

---

## 8. Invariantes que no se tocan

1. **Round-trip byte-perfecto**: el wizard sigue habilitando `Confirmar` solo si la
   reconstrucción da bytes idénticos al original.
2. **Backup antes de cada guardado**, y guardado verificado por relectura.
3. **Historial**: cada cambio individual se registra, aunque la acción del usuario haya
   sido una sola (una importación, una edición masiva).
4. **Campos ocultos**: viajan con cada registro y nunca se editan.
5. **Detección de edición externa** por hash antes de sobrescribir.
6. **Sidecar de metadatos** separado del archivo de la máquina.

---

## 9. Supuestos y preguntas abiertas

### 9.1 Supuestos que se toman por defecto

Si no hay indicación en contra, se implementa así:

1. **Panel multi-máquina**: el Dashboard actual pasa a ser el panel, con las mismas cinco
   columnas del escritorio (Máquina, Registros, Última modificación, Duplicados, Alertas
   de salud). Desde la pantalla de una máquina, `📊 Panel` navega al Dashboard en lugar de
   abrir un modal duplicado, y `🗂 Máquinas` sí abre el selector como modal.
2. **Importación y exportación**: la elección del archivo pasa a ser una subida del
   navegador, y la exportación una descarga. No hay explorador de Windows.
3. **Usuario del historial**: se sigue tomando del sistema operativo del backend, un
   operario por PC, como hoy. El parámetro queda explícito por si más adelante hay login.
4. **Idioma y textos**: se copian literalmente los mensajes, ayudas y tooltips del
   escritorio, porque ya están probados en planta.

### 9.2 Preguntas que quedan

1. **Diálogo de conflicto por edición externa**: en el escritorio ofrece ver diferencias,
   recargar desde disco o sobrescribir. ¿Se mantienen las tres opciones en la web, o se
   quita "sobrescribir con lo mío" por ser la más peligrosa cuando hay varias pestañas?
2. **Alcance de deshacer con varias pestañas**: la pila vive en el backend, así que una
   pestaña puede deshacer lo que hizo otra. ¿Está bien así, o conviene avisar en la barra
   de estado cuándo el último comando lo hizo otra pestaña?
3. **Retención de sesiones de importación**: cuánto tiempo debe seguir viva una
   importación a medio revisar si el operario se va a almorzar. Propuesta: 30 minutos.
4. **Modo oscuro**: no está en el escritorio. ¿Se agrega, dado que la paleta nueva lo
   permite sin esfuerzo, o se deja fuera para no dividir la atención?
