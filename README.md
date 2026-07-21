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
- **Buscador** por el código/identificador de cada registro (Ctrl+F).
- **Nuevo / Editar / Eliminar** registros (campos del diálogo según el perfil).
- **Duplicados** (si el perfil lo activa): agrupa códigos parecidos, permite
  **copiar el código** para buscarlo en SAP, marcar **"No es duplicado"** o
  eliminar los que sí lo sean.
- **Importar cambios**: lee un Excel de formato variable, mapea sus columnas a
  los campos del perfil (sugerencia automática por nombre) y muestra solo los
  registros que difieren para que elijas cuáles aplicar. El mapeo es
  **parcial**: solo el código es obligatorio, el resto de los datos es
  opcional (podés dejar "no importar" en los que ese Excel no trae, por
  ejemplo si solo cambian los "Gramos de Carga" y no el "Color" ni la
  "Velocidad") — los campos no mapeados nunca se comparan ni se modifican.
- **Guardado automático** y **Exportar** el archivo actual u original a
  cualquier carpeta, siempre en el **formato exacto** que espera la máquina.
- **Restaurar original**.

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
│  ├─ profile.py              Carga y valida el perfil JSON.
│  ├─ datastore.py            Motor genérico: lee/reconstruye byte-fiel según perfil.
│  ├─ metadata.py             Sidecar de metadatos de la app (no toca el CSV).
│  ├─ excel_import.py         Importación desde Excel (mapeo por perfil, difflib).
│  ├─ profile_builder.py      Genera un perfil borrador a partir de un CSV adjuntado.
│  ├─ paths.py                Rutas de perfiles y datos (dev y empaquetado).
│  └─ app.py                  Interfaz Tkinter con UI dinámica + selector de máquina.
├─ tests/
│  └─ test_engine.py          Red de seguridad (round-trip byte-perfecto, CRUD, etc.)
├─ run.bat / build.bat
└─ datos/<id_maquina>/        Generado por la app: original + actual + meta.json
```

**Clave de diseño:** el archivo que se sube al HMI se reconstruye *byte por byte*
igual al original (verificado por `tests/test_engine.py`). Los metadatos propios
de la app (marca "no es duplicado", etc.) viven en `datos/<id>/meta.json`, un
archivo aparte que **nunca** se mezcla con el CSV de la máquina.

### Anatomía de un perfil

Un perfil describe el formato sin cablearlo en el código. El de la 232
(`profiles/maquina_232.json`) declara: orientación (transpuesta), delimitador,
encoding, fin de línea, las filas fijas de metadatos, la fila de índice, y cada
campo (`code`, `color`, `grams`, `speed`) con su ubicación, tipo y título. El
motor soporta también archivos **normales** (fila por registro), listos para
cuando aparezca el formato de otra máquina.

Ejecutá `py tests/test_engine.py` para correr la red de seguridad.

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
  `openpyxl` arranca igual pero "Importar cambios" avisa que falta.

---

## Datos históricos de la 232

- `recetas232.csv` — archivo fuente limpio (673 piezas, embebido en el `.exe`).
- `recetas232_backup_original.csv` — CSV de fábrica tal cual llegó (con los 1070
  slots vacíos `_DATA_N`), por si hace falta volver al origen.
- Si existía una carpeta `datos232/` de una versión anterior, la app la **migra
  automáticamente** a `datos/232/` la primera vez (y pasa las marcas de
  "no es duplicado" al nuevo `meta.json`).
