# Plan: Generador masivo de archivos desde plantilla + listado

> Estado: BORRADOR EN CONSTRUCCIÓN. Este documento se va completando a medida
> que definimos los criterios con los ingenieros. Las secciones marcadas
> **(TBD)** dependen de respuestas todavía pendientes.

## 1. Objetivo

Dado:
- una **plantilla** (un archivo de ejemplo ya completo, en `.txt`, `.csv` o
  `.xlsx`), y
- un **listado** de registros (también `.txt`, `.csv` o `.xlsx`, no
  necesariamente del mismo tipo que la plantilla),

generar **un archivo por registro del listado**, con:
- el mismo contenido que la plantilla salvo los valores que ese registro
  reemplaza,
- el mismo tipo de archivo y extensión que la plantilla (nunca el del
  listado),
- un nombre de archivo derivado de uno de los valores del propio registro.

Caso de referencia usado para diseñar esto:
- Plantilla: [docs/Recetas/plantilla.txt](docs/Recetas/plantilla.txt)
- Listado: [docs/Recetas_Andon.txt](docs/Recetas_Andon.txt)

## 2. Precedentes en el código (para no reinventar lo que ya existe)

- **`máquina232/src/profile.py`**: motor genérico de perfiles JSON que describe
  el formato de un archivo de parámetros (orientación columnas/filas, tipos de
  campo, reconstrucción byte a byte). Pensado para leer/escribir catálogos de
  máquina, no para "mail merge" de muchos archivos de salida, pero el enfoque
  de "perfil declarativo describe el formato" es un antecedente directo.
- **`Diagramadora/ai/csv_recipe.py`**: lee un CSV tipo "matriz receta"
  (parámetro x producto), permite editarlo vía Excel y reconstruye el
  original cambiando **solo** las celdas tocadas, con autoverificación
  releyendo el archivo generado. Buena referencia para el criterio de
  seguridad ("no regenerar desde cero", "listar cada cambio", "revalidar
  después de escribir").
- **`backend/app/services/import_service.py`** + `ImportarDialog.tsx`: flujo
  de importación de Excel/CSV al catálogo de máquinas (mapeo de columnas →
  campos, revisión de diferencias, aplicar). No genera archivos nuevos, pero
  es el precedente de UI más cercano para "subir un archivo, mapear columnas,
  revisar antes de confirmar".

Ninguno de los tres resuelve el caso de "un archivo de entrada → N archivos de
salida con nombre variable", así que esto es un motor nuevo.

## 3. Caso de ejemplo: qué se pudo inferir y qué no

`plantilla.txt`:
```
#Codigo;0049810086 //Cambiar código de sellado, a su vez es el nombre del archivo
#Operacion;19
#Descripcion;824903021361 //cambiar código de amortiguador

* #Maquina;<idMaquinas>;<default>;<GPH>;<TEP>;<MUL>;<DIV>
#Maquina;1200009;True;;19.40;1;1
```

`Recetas_Andon.txt` (14 filas, 3 columnas sin encabezado), ej.:
```
301700019344    001789002162    GPS2
481700020049    001789002368    HD
```

Inferencias razonables:
- `#Codigo` es el campo que varía por registro y **también** da nombre al
  archivo de salida (dice explícitamente "a su vez es el nombre del
  archivo").
- `#Descripcion` es el "código de amortiguador", también variable.
- La línea `* #Maquina;<idMaquinas>;<default>;<GPH>;<TEP>;<MUL>;<DIV>` es una
  **leyenda para humanos** (empieza con `*`, no es una línea de datos real):
  documenta qué significa cada campo separado por `;` de la línea
  `#Maquina;...` de abajo. Los `<...>` no son placeholders que el motor deba
  reemplazar.

Lo que **no** se pudo inferir solo mirando los dos archivos (por eso son
preguntas para los ingenieros, sección 4):
- Qué columna del listado corresponde a `#Codigo` y cuál a `#Descripcion`
  (los valores de ejemplo no calzan literalmente entre archivos).
- Qué significa la tercera columna (`GPS2` / `HD`) y si participa del archivo
  generado.
- Si `#Operacion` y la línea `#Maquina;...` quedan siempre iguales o también
  varían por registro (el listado solo tiene 3 columnas, no 7).

## 4. Decisiones tomadas y preguntas abiertas

### Ya definido

1. **Alcance/ubicación**: **backend web + front**. No va al motor de
   escritorio de Diagramadora.
2. **Dónde quedan los archivos generados**: el backend arma un **`.zip`**
   con los N archivos y el front dispara la descarga del navegador (mismo
   patrón que `Backups` / `download_url` en `front/src/api.ts`). No hace
   falta guardar copia en el servidor.
3. **Sintaxis de la plantilla — qué campo cambia y con qué se reemplaza**:
   se marca **el valor exacto entre llaves** dentro de la línea, y el
   comentario `//` de esa misma línea documenta el cambio en lenguaje
   natural. Ejemplo:
   ```
   #Codigo;{0049810086} //Cambiar código de sellado, a su vez es el nombre del archivo
   #Descripcion;{824903021361} //cambiar código de amortiguador
   ```
   Cualquier línea del archivo puede tener un `{...}` — no hay una lista
   cerrada de campos modificables, todo lo que se pueda modificar se marca
   así.
4. **Cómo se detecta a qué columna del listado corresponde cada `{...}`**:
   automático, **sin mapeo manual**. Propuesta concreta (a confirmar en la
   sección de abajo): el motor busca, dentro del comentario `//` de esa
   línea, cuál de los encabezados de columna del listado aparece mencionado
   (comparación sin mayúsculas/minúsculas ni acentos) y usa esa columna. Con
   el ejemplo de arriba: el comentario de `#Codigo` menciona "sellado" →
   columna `sellado`; el de `#Descripcion` menciona "amortiguador" →
   columna `amortiguador`.
5. **Columnas de `Recetas_Andon.txt`** (hoy sin fila de encabezado), en
   orden: `amortiguador`, `sellado`, `area` (esta última todavía sin campo
   correspondiente en la plantilla — se va a agregar después, con su propio
   `{...}` y comentario mencionando "área").
6. **Qué columna define el nombre del archivo de salida**: la que su
   comentario dice explícitamente "a su vez es el nombre del archivo"
   (columna `sellado`, vía el campo `#Codigo`).
7. **Nombres de archivo duplicados**: no se aborta — se les agrega un
   identificador al lado (a definir el formato exacto, ver preguntas).
8. **Copia en servidor**: no hace falta, con el `.zip` alcanza.

9. **Encabezados en el listado**: siempre vienen en el archivo (el listado
   real en planta va a incluir la fila `amortiguador;sellado;area`). No hace
   falta una pantalla para asignarlos a mano.
10. **`{...}` sin columna que calce por nombre en el comentario (o con dos
    que calzan)**: se **ignora esa línea** — no bloquea la generación. El
    valor entre llaves se deja igual al de la plantilla (sin las llaves) en
    todos los archivos generados, como si no fuera variable.
11. **Nombres de archivo repetidos**: sufijo correlativo simple —
    `0049810086.txt`, `0049810086_2.txt`, `0049810086_3.txt`.

### Todavía abierto (asunciones de trabajo, corregir si no son correctas)

12. **Alcance de tipos de plantilla para la sintaxis `{...}`**: el caso
    concreto y el único confirmado hasta ahora es `.txt` línea por línea con
    comentarios `//`. Para no bloquear el diseño, la v1 de este plan asume:
    - Plantilla y listado en `.txt`/`.csv` (línea por línea): soportado
      desde el principio.
    - Plantilla o listado en `.xlsx`: **fuera de alcance de la v1**, se
      encara en una segunda etapa si hace falta (la convención `{...}` +
      comentario no tiene un equivalente obvio en una celda de Excel sin
      definir algo nuevo).
    Avisar si esto no es aceptable.
13. **Validaciones además de duplicados**: v1 asume que hace falta, como
    mínimo: fila de encabezado presente, ninguna fila del listado vacía o
    con menos columnas que el encabezado, y un reporte final (lista de
    archivos generados + líneas ignoradas por falta de match, si las hubo)
    antes de armar el `.zip`. Si hace falta algo más específico (formato de
    código, rangos numéricos, etc.) decímelo y lo sumo.

## 5. Alcance propuesto (borrador — sujeto a lo que se defina en la sección 4)

Flujo:
1. Subir/seleccionar la plantilla.
2. Subir/seleccionar el listado.
3. El motor detecta (o el usuario confirma) qué campos de la plantilla son
   variables.
4. Mapeo: qué columna del listado llena cada campo variable + cuál define el
   nombre de archivo.
5. Previsualización: por cada registro, mostrar el archivo resultante (o al
   menos el nombre de archivo y los valores que cambian) antes de escribir
   nada a disco.
6. Generar: escribir los N archivos, con el mismo tipo/extensión que la
   plantilla.
7. Reporte final: archivos creados, duplicados u errores encontrados.

## 6. Diseño técnico

### 6.1 Sintaxis de plantilla (contrato con el usuario)

- Un campo variable se marca envolviendo su valor de ejemplo entre llaves:
  `{valor}`, en cualquier lugar de cualquier línea.
- La línea debe tener un comentario `//` que mencione, en texto libre, el
  nombre de la columna del listado que lo va a reemplazar (comparación
  case-insensitive y sin acentos: "amortiguador" matchea `Amortiguador` o
  `AMORTIGUADOR`).
- Si el comentario menciona el nombre de la columna que además debe dar
  nombre al archivo de salida, se identifica agregando la frase fija
  **"nombre del archivo"** en el comentario (tal como ya aparece en
  `plantilla.txt`). Debe haber exactamente un campo así por plantilla.
- Si una línea con `{...}` no tiene ningún nombre de columna reconocible en
  su comentario (o tiene más de uno), se trata como no-variable: se
  reemplaza `{valor}` por `valor` (se sacan las llaves) y queda igual en
  todos los archivos generados.

### 6.2 Módulo nuevo: `backend/app/ai/plantillas_masivas.py`

Responsabilidades (puro, sin FastAPI ni I/O de sesión, para poder testear
fácil — mismo criterio que `csv_recipe.py`):

```python
@dataclass
class CampoVariable:
    linea_index: int
    columna_listado: str | None   # None si no matcheó ninguna (línea ignorada)
    es_nombre_archivo: bool
    valor_original: str           # lo que había entre llaves

@dataclass
class PlantillaParseada:
    lineas: list[str]             # contenido original, línea por línea
    campos: list[CampoVariable]
    extension: str                # la de salida, tomada de la plantilla

def parsear_plantilla(texto: str, extension: str) -> PlantillaParseada: ...

def leer_listado(contenido: bytes, nombre_archivo: str) -> tuple[list[str], list[dict]]:
    """Devuelve (encabezados, filas) desde .txt/.csv (delimitador auto-detectado,
    reutilizando el mismo criterio de sniff que csv_recipe.py) o .xlsx (openpyxl)."""

@dataclass
class RegistroGenerado:
    nombre_archivo: str
    contenido: str
    fila_origen: int

@dataclass
class ResultadoGeneracion:
    archivos: list[RegistroGenerado]
    lineas_ignoradas: list[int]     # índices de línea sin match, para el reporte
    columnas_sin_uso: list[str]     # columnas del listado que ningún campo usó

def generar(plantilla: PlantillaParseada, encabezados: list[str],
           filas: list[dict]) -> ResultadoGeneracion: ...
```

`generar()` resuelve colisiones de nombre agregando el sufijo correlativo
(`_2`, `_3`, ...) del punto 4.11, y nunca sobreescribe entre sí dentro del
mismo lote.

### 6.3 Servicio + router

- `backend/app/services/plantillas_masivas_service.py`: recibe los dos
  `UploadFile` (plantilla + listado), llama al módulo `ai`, arma el `.zip`
  en memoria (`zipfile.ZipFile` sobre un `io.BytesIO`) y lo devuelve.
- `backend/app/routers/plantillas_masivas.py`:
  `POST /api/plantillas-masivas/generar` — multipart con `plantilla` y
  `listado`. Devuelve el `.zip` como `StreamingResponse`
  (`application/zip`), más un header o endpoint separado con el reporte
  (archivos creados / líneas ignoradas) — a definir si va en un header JSON
  o en un paso previo de "previsualizar" antes de confirmar la descarga.
- Nada se persiste en `_SESIONES` tipo `import_service.py`: al ser un solo
  paso (subir los dos archivos → bajar el zip), no hace falta estado de
  sesión con TTL.

### 6.4 Front

- Pantalla o diálogo nuevo (ej. `front/src/dialogs/GenerarRecetasDialog.tsx`)
  con dos selectores de archivo (plantilla, listado) y un botón "Generar".
- Antes de descargar, mostrar un resumen: cuántos archivos se van a crear,
  qué líneas de la plantilla se ignoraron por no encontrar columna, qué
  columnas del listado no se usaron — para que el ingeniero pueda confirmar
  que el resultado tiene sentido antes de bajarlo.
- Al confirmar, dispara la descarga del `.zip` (mismo patrón que
  `Backups`/`download_url`).

### 6.5 Tests

- Caso base: `plantilla.txt` (una vez editada con `{...}`) +
  `Recetas_Andon.txt` (con fila de encabezado agregada) → 14 archivos
  `.txt`, contenido y nombres esperados fila por fila.
- Casos de error/edge: comentario sin ninguna columna reconocible, dos
  columnas reconocibles en el mismo comentario, dos filas que generan el
  mismo nombre de archivo, listado con una fila con menos columnas que el
  encabezado, encabezado con acentos vs. comentario sin acentos (y
  viceversa).

## 7. Fuera de alcance (por ahora)

- Edición posterior de los archivos generados (eso ya lo cubre el flujo de
  `csv_recipe.py` para recetas existentes).
- Validación semántica contra el catálogo de máquinas (`maquinas_service`).

## 8. Parte 2: generador de recetas por área

Requerimiento adicional: `docs/Recetas/RecetasHD/`, `RecetasGPS1/` y
`RecetasGPS2/` tienen, cada una, varios archivos de ejemplo ya terminados
(sin sintaxis `{...}`), nombrados `<sellado>.<sufijo>.def.txt` (ej.
`004981008610.17.def.txt`, sufijo = número de operación: `15`, `17`, `13.5`,
etc.). Comparando ejemplos con el mismo sufijo y distinto código se confirmó
que, **dentro de una misma área, por sufijo, todo es fijo salvo `#Codigo`
(sellado) y `#Descripcion` (amortiguador)** — `#Operacion` y la(s) línea(s)
`#Maquina;...` (incluido `idMaquinas`) no cambian.

Por cada registro del listado (mismas columnas `sellado`/`amortiguador`/
`área` de la Parte 1) hay que generar **todas** las variantes de su área:
para el sellado `001789002162` (área GPS2, que tiene sufijos `13.5`/`15`/
`17`) salen 3 archivos, reemplazando únicamente `#Codigo`/`#Descripcion`.

Decisiones tomadas:
- El conjunto de sufijos de cada área es el de los `.txt` en el **nivel
  superior** de `RecetasHD`/`RecetasGPS1`/`RecetasGPS2` (confirmado con el
  ingeniero): **HD = {15,17,19,28}**, **GPS1 = {14,15,17,19,26}**, **GPS2 =
  {13.5,15,17}**. Los sufijos con un solo ejemplo (`.28` en HD, `.26` en
  GPS1) también se generalizan a todos los registros de esa área.
- Las subcarpetas `Nuevo`/`Nuevos` no se leen (mismos sufijos que el nivel
  superior, no aportan nada nuevo) y `Obsoletos` tampoco (sufijos que ya no
  se generan).
- A diferencia de la Parte 1, acá no hace falta marcar `{...}` ni comentario
  `//`: el campo variable se identifica por el **nombre del campo**
  (`#Codigo`, `#Descripcion` son siempre los dos que cambian).
- Los archivos de referencia usan CRLF; se detectó que el motor de la Parte
  1 los reconstruía en LF (bug latente para archivos que va a leer un
  equipo) — se corrigió para preservar el fin de línea original, y el motor
  nuevo usa el mismo criterio.
- El usuario solo sube el **listado**; las plantillas de referencia viven en
  el repo (`docs/Recetas/Recetas<AREA>/`) y se leen frescas en cada llamada.
- El `.zip` agrupa los archivos generados en una carpeta por área
  (`HD/...`, `GPS2/...`).

Implementación:
- `backend/app/ai/recetas_por_area.py` — `cargar_catalogo()`,
  `generar_por_area()`. Reutiliza `leer_listado`/`_normalizar`/`_decode`/
  `_detectar_eol` de `plantillas_masivas.py`.
- `backend/app/services/recetas_por_area_service.py` +
  `backend/app/routers/recetas_por_area.py` —
  `POST /api/recetas-por-area/previsualizar` y `/generar`, mismo patrón sin
  sesión que la Parte 1.
- Front: `front/src/pages/RecetasPorArea.tsx` (ruta
  `/recetas-por-area`), más una página `Herramientas.tsx` (ruta
  `/herramientas`) para elegir entre esta herramienta, el generador desde
  plantilla (Parte 1) y "Tabular mediciones" — reemplaza los links sueltos
  del header.
- Tests: `backend/tests/test_recetas_por_area.py` (motor puro, contra los
  archivos reales de `docs/Recetas/`) y
  `test_recetas_por_area_service.py`.
