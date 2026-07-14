# Configurador Máquina 232

Aplicación de escritorio para editar el archivo de recetas (`.csv`) de la
**máquina 232**: los parámetros de calibración de **cantidad de aceite**
(*Gramos de Carga*) y **velocidad de operación** (*Velocidad Inicio*) de cada
pieza que se produce en la planta.

Interfaz simple en blanco / gris / verde hoja. Corre en cualquier PC con
Windows, empaquetable como **un único `.exe` portable**.

---

## Uso rápido

| Quiero… | Hago… |
|---|---|
| **Desarrollar / probar** en esta PC | Doble clic en **`run.bat`** (necesita Python 3 instalado) |
| **Generar el portable** para distribuir | Doble clic en **`build.bat`** → genera `dist\ConfiguradorMaquina232.exe` |
| **Usar el portable** en la planta | Copiar `ConfiguradorMaquina232.exe` a la PC y hacer doble clic |

---

## Qué hace la aplicación

- **Tabla** con todas las piezas y sus parámetros: `Código`, `Color`,
  `Gramos de Carga`, `Velocidad Inicio`.
- **Buscador** por código para encontrar un registro al instante.
- **Nuevo / Editar / Eliminar** registros (los nuevos se agregan al final).
- **Duplicados**: agrupa códigos que coinciden al ignorar los dígitos `0`
  (p. ej. `00049810005962` y `004981005962`), típico de errores de relleno de
  ceros al cargar piezas. Se muestran en grupos con acciones por registro:
  - **Copiar código** → lo copia al portapapeles para buscarlo en SAP y
    confirmar si existe de verdad.
  - **No es duplicado** → lo marca como revisado y lo excluye de futuras
    búsquedas de duplicados (no se borra, sigue en el catálogo).
  - Check + **Eliminar seleccionados** → borra del catálogo los que sí son
    duplicados reales.
  La marca "no es duplicado" se guarda en una fila extra dentro de
  `datos232/actual.csv`, propia de esta app: **nunca se incluye** al exportar
  el CSV para el HMI, que siempre mantiene el formato original de 7 filas de
  la máquina (ver más abajo).
- **Importar cambios**: lee un Excel (`.xlsx`/`.xlsm`) de **formato variable**
  (columnas en cualquier orden o con cualquier nombre) y lo compara contra el
  catálogo actual:
  1. Si el libro tiene varias hojas, primero pregunta cuál usar.
  2. Pide mapear qué columna del Excel es Código, Color, Gramos de Carga y
     Velocidad Inicio (sugiere un mapeo automático según el nombre de
     encabezado, pero el usuario lo confirma).
  3. Busca los registros cuyo código coincide y compara Color/Gramos/Velocidad;
     si el Excel guardó el código como número y perdió ceros a la izquierda,
     también intenta una coincidencia aproximada (avisando que la revises).
  4. Muestra solo los registros que **difieren**, con el valor actual y el
     nuevo lado a lado, para que el usuario marque cuáles aplicar — igual que
     en "Duplicados", nada se cambia automáticamente. Las celdas vacías del
     Excel no pisan el valor actual de ese campo.
- **Guardado automático**: cada cambio se guarda en `datos232/actual.csv`.
- **Exportar** el CSV a cualquier carpeta de la PC, en el **formato exacto**
  del archivo original de la máquina:
  - *CSV actual* → con los últimos cambios.
  - *CSV original* → copia de fábrica sin alterar.
- **Restaurar original**: descarta los cambios y vuelve al archivo de fábrica.

Por defecto la tabla muestra solo las piezas reales. El casillero
*"Mostrar slots vacíos (_DATA_)"* revela los espacios reservados que trae el
archivo de la máquina.

---

## Archivos permanentes

Al iniciar, la app crea una carpeta **`datos232`** junto al ejecutable con:

| Archivo | Rol |
|---|---|
| `original.csv` | Copia del archivo de fábrica. **La app nunca lo modifica.** |
| `actual.csv`   | Archivo de trabajo con los últimos cambios. |

Ambos se pueden exportar desde el botón **Exportar**.

---

## Estructura del proyecto

```
máquina232/
├─ recetas232.csv               Archivo fuente (limpio, queda embebido en el .exe)
├─ recetas232_backup_original.csv  Copia del CSV de fábrica tal cual llegó, sin limpiar
├─ src/
│  ├─ app.py           Interfaz (Tkinter) + lógica de la ventana
│  ├─ recipe_store.py  Carga/guardado fiel al formato de la máquina 232
│  └─ excel_import.py  Lectura de Excel de formato variable (openpyxl)
├─ run.bat             Ejecuta la app desde el código fuente (desarrollo)
├─ build.bat           Genera el .exe portable con PyInstaller
├─ requirements.txt    Dependencias (openpyxl + PyInstaller)
└─ README.md
```

### Limpieza aplicada al `recetas232.csv` fuente

El archivo de fábrica original (conservado intacto en
`recetas232_backup_original.csv`) tenía 1743 columnas, de las cuales 1070 eran
slots vacíos `_DATA_N` sin usar. Sobre el archivo fuente (`recetas232.csv`) se
aplicó:

1. **Eliminación de slots vacíos** `_DATA_N` → quedaron las 673 piezas reales.
2. **Códigos duplicados por relleno de ceros** → quedan sin resolver a propósito;
   se revisan interactivamente con el botón **Duplicados** de la app, porque
   requieren criterio humano (piezas con "código parecido" pueden tener
   parámetros muy distintos y no ser duplicados reales).
3. **Orden alfabético ascendente** (sin distinguir mayúsculas/minúsculas) y
   **renumeración de posiciones** (fila 3 del CSV), para que el catálogo sea
   más fácil de navegar.

---

## Formato del CSV de la máquina 232

El archivo es **transpuesto**: cada **columna** es una pieza y cada **fila** un
parámetro. Son 7 filas, delimitadas por `,`, con saltos de línea `CRLF` y sin BOM:

```
List separator=,Decimal symbol=.,,,,,…        (metadatos)
Recipe_1 ,,,,,…                                (nombre de la receta)
LANGID_409,<código1>,<código2>,…              (código de cada pieza)
3,1,2,3,…                                       (posición secuencial)
Recetas_Datos Ingresados_Color,<v1>,<v2>,…
Recetas_Datos Ingresados_Gramos de Carga,<v1>,<v2>,…
Recetas_Datos Ingresados_Velocidad Inicio,<v1>,<v2>,…
```

La aplicación reconstruye este formato byte por byte al exportar, para que el
archivo resultante sea idéntico en estructura al que espera la máquina.

### Fila extra interna (solo en `datos232/actual.csv`)

El archivo de trabajo (`datos232/actual.csv`) tiene una **8ª fila** que no
existe en el formato de la máquina:

```
Configurador232_RevisadoNoDuplicado,0,1,0,0,…
```

Marca qué códigos el usuario ya revisó y confirmó que **no** son duplicados
(ver función **Duplicados**). Es exclusiva de esta app:

- `original.csv` nunca la tiene (es copia intacta del CSV de fábrica).
- Al usar **Exportar → CSV actual**, la app genera el archivo con el formato
  original de 7 filas, sin esta fila extra — es el que hay que subir al HMI.
- Si abrís un `actual.csv` viejo de 7 filas (de antes de esta función), la
  app lo carga igual y asume que ningún registro fue revisado todavía.

---

## Requisitos

- **Para el `.exe` portable:** nada. Es autónomo (incluye openpyxl embebido).
- **Para desarrollo / build:** [Python 3](https://www.python.org/downloads/)
  (marcar *"Add Python to PATH"* al instalar). Tkinter viene incluido;
  `run.bat` y `build.bat` instalan `openpyxl` automáticamente la primera vez.
  Si falta, la app funciona igual pero "Importar cambios" avisa que no está
  disponible.
