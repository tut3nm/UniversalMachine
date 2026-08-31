# Configurador de Parámetros de Planta

Aplicación de escritorio para editar los archivos de parámetros de las máquinas
de la planta. Es **genérica**: cada máquina se describe con un **perfil JSON**
que le dice a la app cómo leer y reconstruir su archivo (formato, columnas,
parámetros). La primera máquina soportada es la **232** (calibración de aceite
y velocidad), pero se pueden agregar más sin tocar el código.

Interfaz simple en blanco / gris / verde hoja, con [ttkbootstrap](https://ttkbootstrap.readthedocs.io/)
(liviana, ~1.7 MB, sin dependencias compiladas) para botones planos, tooltips
en cada acción y notificaciones tipo "toast" al confirmar cambios. Corre en
cualquier PC con Windows, empaquetable como **un único `.exe` portable**.

---

## Uso rápido

| Quiero… | Hago… |
|---|---|
| **Desarrollar / probar** en esta PC | Doble clic en **`run.bat`** (necesita Python 3) |
| **Generar el portable** para distribuir | Doble clic en **`build.bat`** → genera `dist\ConfiguradorPlanta.exe` |
| **Usar el portable** en la planta | Copiar `ConfiguradorPlanta.exe` a la PC y hacer doble clic |

El botón **🗂 Máquinas** (arriba a la derecha) siempre está disponible: abre el
navegador de documentos de configuración, marca cuál es la máquina activa, y
desde ahí también se agregan máquinas nuevas.

---

## Qué hace la aplicación

- **Tabla dinámica**: las columnas salen del perfil de la máquina elegida.
- **Buscador** por cualquier campo visible (no solo el código, Ctrl+F), con
  **filtros de rango numérico** y filtros frecuentes guardables por máquina.
- **Nuevo / Editar / Eliminar** registros. Los parámetros también se pueden
  editar **en línea** (doble clic sobre la celda, sin abrir el diálogo
  completo) o **en masa** (mismo valor a varios registros seleccionados de
  una vez, como un solo paso deshacible).
- **Deshacer / Rehacer** en sesión (Ctrl+Z / Ctrl+Y) para alta, edición, baja
  e importación.
- **Duplicados** (si el perfil lo activa): agrupa códigos parecidos, permite
  **copiar el código** para buscarlo en SAP, marcar **"No es duplicado"** o
  eliminar los que sí lo sean.
- **Importar cambios**: lee un Excel o **CSV** de formato variable, mapea sus
  columnas a los campos del perfil (sugerencia automática por nombre, y
  recuerda el último mapeo confirmado por máquina) con una **vista previa**
  de las primeras filas, y muestra solo los registros que difieren para que
  elijas cuáles aplicar. El mapeo es **parcial**: solo el código es
  obligatorio, el resto es opcional. Avisa si algo se redondeó al importar un
  decimal a un campo entero, y entiende separadores de miles regionales.
- **Ver cambios**: compara `actual` contra `original` campo por campo (altas,
  bajas, modificaciones), con filtro por tipo y exportación a CSV.
- **Salud del catálogo**: de una sola pasada, lista valores fuera de rango,
  campos obligatorios vacíos, duplicados sin revisar y slots libres, con
  acceso directo al registro desde cada hallazgo.
- **Backups automáticos** en cada guardado (con retención: todos los de hoy +
  uno por día + uno por mes) e **historial de cambios** consultable y
  filtrable, con informe exportable a CSV (fecha, usuario, valores
  anteriores/nuevos, versión de la app).
- **Detección de modificación externa**: si `actual.<ext>` cambió por fuera
  de la app desde la última lectura/escritura, avisa antes de pisarlo y deja
  elegir entre ver las diferencias, recargar desde disco o sobrescribir.
- **Instancia única por máquina**: no deja abrir la misma máquina dos veces
  en la misma PC (evita que una ventana pise los cambios de la otra).
- **Panel multi-máquina** (con 3 o más máquinas configuradas): vista
  consolidada de última modificación, registros, duplicados pendientes y
  alertas de salud de cada una.
- **Guardado automático** y **Exportar** el archivo actual u original a
  cualquier carpeta, siempre en el **formato exacto** que espera la máquina.
- **Restaurar original** o un **backup** puntual.

### Sobre la interfaz

- Cada botón de la barra de herramientas tiene un **tooltip** (pasar el mouse
  por encima) que explica qué hace y su atajo de teclado, si tiene.
- Los botones están agrupados por función — alta de datos (Nuevo/Editar/Eliminar),
  calidad de datos (Duplicados/Importar) y archivo (Exportar/Restaurar) —
  separados visualmente para que sea fácil ubicar cada acción de un vistazo.
- Las confirmaciones (guardar, exportar, importar) aparecen como una
  **notificación breve** en la esquina, sin interrumpir con un cuadro de
  diálogo modal; las acciones que sí requieren confirmación (eliminar,
  restaurar) siguen preguntando antes de aplicarse.

---

## Cómo funciona (arquitectura)

```
proyecto/
├─ profiles/                  Perfiles de máquina (JSON). Se pueden agregar más.
│  └─ maquina_232.json
├─ recetas232.csv             Archivo de muestra embebido para sembrar la 232.
├─ src/
│  ├─ app.py                  Interfaz Tkinter: UI dinámica, selector de máquina, diálogos.
│  ├─ profile.py              Carga y valida el perfil JSON.
│  ├─ datastore.py            Motor genérico: lee/reconstruye byte-fiel según perfil.
│  ├─ metadata.py             Sidecar de metadatos de la app (no toca el CSV).
│  ├─ io_seguro.py            Escritura atómica (nunca deja un archivo a medio escribir).
│  ├─ validacion.py           Validación de rango de un valor o de un registro completo.
│  ├─ backups.py              Backups automáticos rotativos por guardado.
│  ├─ historial.py            Historial de cambios (datos/<id>/historial.jsonl).
│  ├─ informe.py               Exporta eventos del historial a CSV.
│  ├─ diferencias.py          Compara `actual` contra `original` campo por campo.
│  ├─ deteccion_externa.py    Hash de archivo para detectar modificación externa.
│  ├─ instancia.py            Lock de instancia única por máquina (datos/<id>/.lock).
│  ├─ salud.py                Reporte de salud del catálogo (rangos, vacíos, duplicados).
│  ├─ panel_multi_maquina.py  Resumen consolidado de todas las máquinas configuradas.
│  ├─ filtros.py              Búsqueda por cualquier campo, filtros de rango, presets.
│  ├─ excel_import.py         Importación desde Excel/CSV (mapeo por perfil, difflib).
│  ├─ import_mapeos.py        Recuerda el último mapeo de columnas usado por máquina.
│  ├─ importacion.py          Cálculo de diferencias entre el catálogo y un Excel/CSV.
│  ├─ arranque.py             Seed y migración de datos al activar una máquina.
│  ├─ profile_builder.py      Genera un perfil borrador a partir de un CSV adjuntado.
│  ├─ paths.py                Rutas de perfiles y datos (dev y empaquetado).
│  ├─ log_config.py           Logging a datos/log/, con manejador de excepciones no capturadas.
│  └─ version.py              Versión de la app y fecha de compilación.
├─ tests/                     Un archivo por módulo, más varios test_app_*.py de integración
│  ├─ test_engine.py          Red de seguridad (round-trip byte-perfecto, CRUD, etc.)
│  └─ test_synthetic.py       Variantes de formato con datos inventados (no depende de los CSV reales)
├─ requirements-dev.txt       Dependencias solo para tests (pytest)
├─ .github/workflows/tests.yml  CI: pytest en cada push/PR, build del .exe en cada tag
├─ run.bat / build.bat
└─ datos/<id_maquina>/        Generado por la app: original + actual + meta.json + backups/ + historial.jsonl
```

**Clave de diseño:** el archivo que se sube al HMI se reconstruye *byte por byte*
igual al original (verificado por `tests/test_engine.py`), y se escribe siempre
de forma atómica (`io_seguro.py`) para que nunca quede a medio escribir. Los
metadatos propios de la app (marca "no es duplicado", etc.) viven en
`datos/<id>/meta.json`, un archivo aparte que **nunca** se mezcla con el CSV de
la máquina. El detalle de cada nivel de mejora implementado (integridad de
datos, recuperabilidad/historial, confiabilidad del proceso, funcionalidad
nueva) está documentado en [`PLAN_MEJORAS.md`](PLAN_MEJORAS.md).

### Anatomía de un perfil

Un perfil describe el formato sin cablearlo en el código. El de la 232
(`profiles/maquina_232.json`) declara: orientación (transpuesta), delimitador,
encoding, fin de línea, las filas fijas de metadatos, la fila de índice, y cada
campo (`code`, `color`, `grams`, `speed`) con su ubicación, tipo y título. El
motor soporta también archivos **normales** (fila por registro), listos para
cuando aparezca el formato de otra máquina.

Ejecutá `py -m pip install -r requirements-dev.txt` una vez, y después `pytest`
(o `py tests/test_engine.py`, que sigue andando suelto) para correr la red de
seguridad. `tests/test_synthetic.py` cubre además variantes de formato (CRLF/LF/CR,
con/sin BOM, delimitador `,`/`;`, campos ocultos, placeholders) con datos
inventados, para que la suite no dependa de que los CSV reales de planta estén
presentes.

### Agregar una máquina nueva

Desde **🗂 Máquinas → ➕ Agregar máquina**: adjuntás el CSV de la máquina,
elegís si es "fila por pieza" (CSV normal, con encabezado) o "columna por
pieza" (transpuesto, como la 232 — pidiendo en qué fila está el código), y la
app:

1. Detecta automáticamente delimitador, codificación y fin de línea del archivo.
2. Genera un **perfil borrador** (`profiles/maquina_<id>.json`) con un campo
   por cada columna/fila detectada (nombre, tipo `entero`/`decimal`/`texto`
   adivinado por muestreo).
3. Crea `datos/<id>/` y siembra `original.csv` / `actual.csv` con el archivo
   adjuntado.

Esto es un punto de partida **funcional pero aproximado**: no distingue filas
de metadatos fijos, IDs, etc. — eso lo termina de ajustar un ingeniero editando
el JSON a mano (ver la anatomía de un perfil arriba), o el **asistente visual
paso a paso** que se construirá más adelante, cuando haya archivos de
referencia de más máquinas para validar ese diseño contra un caso real.

---

## Requisitos

- **Para el `.exe` portable:** nada. Es autónomo (incluye ttkbootstrap,
  openpyxl y los perfiles).
- **Para desarrollo / build:** [Python 3](https://www.python.org/downloads/)
  (marcar *"Add Python to PATH"*). Tkinter viene incluido; `run.bat` y
  `build.bat` instalan `ttkbootstrap` y `openpyxl` automáticamente.
  Sin `ttkbootstrap` la app no arranca (es la base de la interfaz); sin
  `openpyxl` arranca igual y hasta se puede importar desde **CSV** —
  solo falla si se intenta abrir un `.xlsx`/`.xlsm` sin tenerlo instalado.

---

## Datos históricos de la 232

- `recetas232.csv` — archivo fuente limpio (673 piezas, embebido en el `.exe`).
- `recetas232_backup_original.csv` — CSV de fábrica tal cual llegó (con los 1070
  slots vacíos `_DATA_N`), por si hace falta volver al origen.
- Si existía una carpeta `datos232/` de una versión anterior, la app la **migra
  automáticamente** a `datos/232/` la primera vez (y pasa las marcas de
  "no es duplicado" al nuevo `meta.json`).
