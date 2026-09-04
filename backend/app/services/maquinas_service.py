"""Capa de servicio: adapta profile.py/datastore.py/backups.py/historial.py
(Python puro, dataclasses) a dicts JSON-friendly para los routers de
FastAPI. Sigue el modelo "sin estado entre requests": cada operación
carga el DataStore desde disco, opera, guarda — no hay un DataStore vivo
en memoria del proceso (a diferencia de la app Tkinter). Esto es a
propósito: permite múltiples pestañas/clientes sin sincronizar estado de
sesión, al costo de recargar el archivo en cada request (aceptable para
los tamaños de catálogo actuales, cientos-miles de registros)."""

from __future__ import annotations

import dataclasses
import os
from typing import Any

from app import _bootstrap  # noqa: F401  (side effect: agrega app/core/ a sys.path)

import arranque
import backups as backups_mod
import deteccion_externa
import filtros as filtros_mod
import historial as historial_mod
import panel_multi_maquina
import paths
import salud as salud_mod
from datastore import DataStore
from metadata import Sidecar
from profile import Campo, Profile, ProfileError
from validacion import ErrorValidacion, parsear_valor_campo, validar_valores_de_registro

APP_VERSION = "webapp-0.1.0"

# Tope de filas por request. La tabla del frontend pide ventanas de 200 a
# medida que el operario baja; el tope existe para que un cliente no pueda
# pedir un catálogo entero de miles de registros de una sola vez.
LIMITE_MAXIMO = 1000


class MaquinaNoEncontrada(Exception):
    pass


class ConflictoEdicionExterna(Exception):
    """El archivo en disco cambió desde el último hash conocido del cliente."""


class ValoresInvalidos(Exception):
    def __init__(self, errores: list):
        self.errores = errores
        super().__init__("; ".join(f"{e.titulo_ui}: {e.mensaje}" for e in errores))


class ClaveDuplicada(Exception):
    """Ya existe un registro con esa clave — el mismo chequeo que hace
    `RecordDialog._on_ok` en el escritorio (máquina232/src/app.py:1377)
    antes de aceptar un alta o edición."""

    def __init__(self, titulo_ui: str, valor: str, posicion: int):
        self.titulo_ui = titulo_ui
        self.valor = valor
        self.posicion = posicion
        super().__init__(
            f"Ya existe un registro con {titulo_ui} «{valor}» (posición {posicion}).")


def _perfil_path(machine_id: str) -> str:
    return os.path.join(paths.profiles_dir(), f"maquina_{machine_id}.json")


def _rutas(profile: Profile) -> tuple[str, str, str]:
    d = paths.data_dir_for(profile.id)
    ext = profile.extension
    return (
        os.path.join(d, f"actual.{ext}"),
        os.path.join(d, f"original.{ext}"),
        os.path.join(d, "meta.json"),
    )


def _listar_ids() -> list[str]:
    pdir = paths.profiles_dir()
    ids = []
    for name in os.listdir(pdir):
        if name.startswith("maquina_") and name.endswith(".json"):
            ids.append(name[len("maquina_"):-len(".json")])
    return sorted(ids)


def cargar_perfil(machine_id: str) -> Profile:
    path = _perfil_path(machine_id)
    if not os.path.exists(path):
        raise MaquinaNoEncontrada(machine_id)
    return Profile.load(path)


def _asegurar_sembrado(profile: Profile) -> None:
    actual, original, meta = _rutas(profile)
    if not os.path.exists(actual):
        arranque.seed_or_migrate(profile, original, actual, meta)


def _cargar_store(profile: Profile) -> DataStore:
    """Carga fresca desde disco. La usan las rutas que MUTAN: nunca deben
    tocar el objeto que quedó cacheado para lecturas."""
    _asegurar_sembrado(profile)
    actual, _, _ = _rutas(profile)
    return DataStore.load(actual, profile)


# Caché de solo lectura: {ruta: (firma_del_archivo, DataStore)}. Recorrer la
# tabla pide una ventana de filas por vez, y sin esto cada scroll volvería a
# parsear el CSV entero. La firma incluye mtime y tamaño, así que la entrada
# se invalida sola cuando el archivo cambia — lo cambie esta app u otro
# programa por fuera, que es justo lo que detecta deteccion_externa.
_CACHE_LECTURA: dict[str, tuple[tuple[int, int], DataStore]] = {}


def _firma_archivo(path: str) -> tuple[int, int] | None:
    try:
        st = os.stat(path)
    except OSError:
        return None
    return (st.st_mtime_ns, st.st_size)


def _cargar_store_cacheado(profile: Profile) -> DataStore:
    """Igual que `_cargar_store` pero reutiliza el último DataStore leído si
    el archivo no cambió. SOLO para lecturas: quien vaya a mutar tiene que
    pedir una copia propia con `_cargar_store`."""
    _asegurar_sembrado(profile)
    actual, _, _ = _rutas(profile)
    firma = _firma_archivo(actual)
    if firma is not None:
        guardado = _CACHE_LECTURA.get(actual)
        if guardado is not None and guardado[0] == firma:
            return guardado[1]
    store = DataStore.load(actual, profile)
    if firma is not None:
        _CACHE_LECTURA[actual] = (firma, store)
    return store


def listar_maquinas() -> list[dict[str, Any]]:
    perfiles = []
    for mid in _listar_ids():
        try:
            perfiles.append(cargar_perfil(mid))
        except ProfileError:
            continue
    resumenes = panel_multi_maquina.resumen_de_todas(perfiles)
    return [dataclasses.asdict(r) for r in resumenes]


def obtener_maquina(machine_id: str) -> dict[str, Any]:
    """Todo lo que la UI necesita saber del perfil para armarse sola: los
    campos visibles (con tipo, rango y formato) y los interruptores que en el
    escritorio deciden qué botones existen — el toggle de slots vacíos solo
    aparece si el perfil define un patrón de placeholder, y el botón de
    duplicados solo si el perfil declara esa feature (app.py:3502, 3452)."""
    profile = cargar_perfil(machine_id)
    return {
        "id": profile.id,
        "nombre": profile.nombre,
        "descripcion": profile.descripcion,
        "extension": profile.extension,
        "orientacion": profile.orientacion,
        "archivo_inicial": profile.archivo_inicial,
        "tiene_placeholders": profile.placeholder_regex() is not None,
        "tiene_duplicados": profile.duplicados_config() is not None,
        "campos": [dataclasses.asdict(c) for c in profile.campos_visibles()],
    }


class FiltroInvalido(ValueError):
    """Un parámetro de filtro/orden no corresponde al perfil de la máquina."""


def parsear_rangos(profile: Profile, crudos: list[str] | None) -> dict[str, tuple]:
    """`["grams:0:500", "speed::400"]` -> `{"grams": (0.0, 500.0),
    "speed": (None, 400.0)}`, con el mismo formato que espera
    `filtros.coincide_rangos`. Un extremo vacío es "sin límite de ese lado"."""
    rangos: dict[str, tuple] = {}
    for crudo in crudos or []:
        partes = crudo.split(":")
        if len(partes) != 3:
            raise FiltroInvalido(
                f"Rango mal formado: '{crudo}'. Se espera 'campo:min:max'.")
        nombre, texto_min, texto_max = (p.strip() for p in partes)
        campo = profile.campo_por_nombre(nombre)
        if campo is None or not campo.es_numerico:
            raise FiltroInvalido(f"'{nombre}' no es un campo numérico de esta máquina.")
        try:
            minimo = float(texto_min) if texto_min else None
            maximo = float(texto_max) if texto_max else None
        except ValueError:
            raise FiltroInvalido(f"Los límites de '{nombre}' deben ser números.") from None
        if minimo is None and maximo is None:
            continue  # un rango sin ningún límite no filtra nada
        rangos[nombre] = (minimo, maximo)
    return rangos


def _filas_visibles(profile: Profile, store: DataStore, q: str,
                    rangos: dict[str, tuple], placeholders: bool) -> list[tuple[int, dict]]:
    """Mismo criterio que `App._visible_rows` del escritorio
    (máquina232/src/app.py:3564): oculta slots vacíos salvo que se pidan,
    aplica la búsqueda libre y después los rangos numéricos."""
    campos_visibles = profile.campos_visibles()
    tiene_ph = profile.placeholder_regex() is not None
    query = (q or "").strip().lower()
    out: list[tuple[int, dict]] = []
    for i, rec in enumerate(store.records):
        if tiene_ph and not placeholders and store.is_placeholder(rec):
            continue
        if not filtros_mod.coincide_busqueda(rec, campos_visibles, query):
            continue
        if rangos and not filtros_mod.coincide_rangos(rec, rangos):
            continue
        out.append((i, rec))
    return out


def _ordenar(filas: list[tuple[int, dict]], profile: Profile,
             orden: str | None, descendente: bool) -> list[tuple[int, dict]]:
    """Orden por columna, con el mismo criterio que el escritorio: numérico
    real en los campos numéricos (y los vacíos al final), alfabético sin
    distinguir mayúsculas en el resto. Sin `orden`, queda el del archivo."""
    if not orden:
        return filas
    if orden == "pos":
        return sorted(filas, key=lambda t: t[0], reverse=descendente)
    campo: Campo | None = profile.campo_por_nombre(orden)
    if campo is None or not campo.visible:
        raise FiltroInvalido(f"'{orden}' no es una columna visible de esta máquina.")
    if campo.es_numerico:
        def clave(t: tuple[int, dict]):
            valor = t[1].get(orden)
            return (valor is None, valor if valor is not None else 0)
    else:
        def clave(t: tuple[int, dict]):
            return (False, str(t[1].get(orden, "")).lower())
    return sorted(filas, key=clave, reverse=descendente)


def _serializar(store: DataStore, campos_visibles: set[str],
                filas: list[tuple[int, dict]], desde: int) -> list[dict[str, Any]]:
    salida = []
    for n, (i, rec) in enumerate(filas, start=desde + 1):
        salida.append({
            "index": i,       # posición real en el archivo: con esto se muta
            "pos": n,         # posición en la lista filtrada y ordenada
            "es_placeholder": store.is_placeholder(rec),
            **{k: v for k, v in rec.items() if k in campos_visibles},
        })
    return salida


def listar_registros(machine_id: str, q: str = "", rangos_crudos: list[str] | None = None,
                     placeholders: bool = False, orden: str | None = None,
                     descendente: bool = False, offset: int = 0,
                     limit: int = 200) -> dict[str, Any]:
    """Una ventana del catálogo, ya filtrada y ordenada por el servidor. La
    tabla del frontend es virtualizada y pide ventanas a medida que el
    operario se desplaza: el catálogo más grande de planta supera los 5000
    registros y mandarlo entero en cada carga no escala."""
    profile = cargar_perfil(machine_id)
    store = _cargar_store_cacheado(profile)
    actual, _, _ = _rutas(profile)
    rangos = parsear_rangos(profile, rangos_crudos)
    filas = _ordenar(
        _filas_visibles(profile, store, q, rangos, placeholders),
        profile, orden, descendente)

    offset = max(0, offset)
    limit = max(1, min(limit, LIMITE_MAXIMO))
    ventana = filas[offset:offset + limit]
    campos_visibles = {c.nombre_interno for c in profile.campos_visibles()}
    return {
        "registros": _serializar(store, campos_visibles, ventana, offset),
        "ventana": {"offset": offset, "limit": limit},
        "totales": {
            "mostrados": len(filas),
            "reales": store.count_real(),
            "total": len(store.records),
        },
        "advertencias": list(store.advertencias),
        "hash": deteccion_externa.hash_archivo(actual) if os.path.exists(actual) else None,
    }


def indices_filtrados(machine_id: str, q: str = "", rangos_crudos: list[str] | None = None,
                      placeholders: bool = False, orden: str | None = None,
                      descendente: bool = False) -> dict[str, Any]:
    """Todos los índices que matchean el filtro actual, en el orden en que se
    ven. Es lo que necesita "seleccionar todo lo filtrado" sin obligar al
    operario a bajar miles de filas para marcarlas a mano."""
    profile = cargar_perfil(machine_id)
    store = _cargar_store_cacheado(profile)
    rangos = parsear_rangos(profile, rangos_crudos)
    filas = _ordenar(
        _filas_visibles(profile, store, q, rangos, placeholders),
        profile, orden, descendente)
    return {"indices": [i for i, _ in filas]}


_ACCION_HISTORIAL = {"alta": "alta", "edicion": "modificacion", "baja": "baja"}


@dataclasses.dataclass
class CambioRegistro:
    """Un cambio puntual sobre UN registro — el equivalente de
    `CambioRegistro` en el escritorio (máquina232/src/app.py:69), sin la
    pila de deshacer (todavía no portada, ver PLAN_PARIDAD_UI.md 5.3)."""
    accion: str  # "alta" | "edicion" | "baja"
    clave: str
    antes: dict | None = None
    despues: dict | None = None


def _guardar_con_backup(profile: Profile, store: DataStore,
                         cambios: list[CambioRegistro],
                         hash_esperado: str | None) -> str:
    """Un solo backup y un solo guardado para TODOS los cambios de la
    operación (una edición en masa de 40 registros no crea 40 backups), pero
    un evento de historial POR REGISTRO — igual que `_registrar_cambios` en
    el escritorio (máquina232/src/app.py:3051): cada alta/edición/baja queda
    trazada individualmente aunque el usuario la haya disparado de una."""
    actual, _, _ = _rutas(profile)
    if hash_esperado is not None and os.path.exists(actual):
        if deteccion_externa.fue_modificado_externamente(actual, hash_esperado):
            raise ConflictoEdicionExterna(
                "El archivo fue modificado por fuera de la app desde la última carga.")
    data_dir = paths.data_dir_for(profile.id)
    backups_mod.crear_backup(data_dir, actual, profile.extension)
    store.save(actual)
    path_historial = os.path.join(data_dir, "historial.jsonl")
    for c in cambios:
        historial_mod.registrar(
            path_historial, accion=_ACCION_HISTORIAL[c.accion], clave=c.clave,
            anteriores=c.antes, nuevos=c.despues, origen="webapp", version=APP_VERSION,
        )
    return deteccion_externa.hash_archivo(actual)


def _verificar_clave_no_duplicada(profile: Profile, store: DataStore, clave_valor: str,
                                  exclude_index: int | None = None) -> None:
    dup = store.find_key(clave_valor, exclude_index=exclude_index)
    if dup != -1:
        raise ClaveDuplicada(profile.campo_clave().titulo_ui, clave_valor, dup + 1)


def crear_registro(machine_id: str, valores: dict[str, Any],
                    hash_esperado: str | None = None) -> dict[str, Any]:
    profile = cargar_perfil(machine_id)
    errores = validar_valores_de_registro(profile, valores)
    if errores:
        raise ValoresInvalidos(errores)
    store = _cargar_store(profile)
    nuevo = store.nuevo_registro(valores)
    _verificar_clave_no_duplicada(profile, store, store.key_of(nuevo))
    store.add(nuevo)
    idx = len(store.records) - 1
    nuevo_hash = _guardar_con_backup(
        profile, store, [CambioRegistro("alta", store.key_of(nuevo), None, nuevo)],
        hash_esperado)
    return {"index": idx, "registro": nuevo, "hash": nuevo_hash}


def actualizar_registro(machine_id: str, index: int, valores: dict[str, Any],
                         hash_esperado: str | None = None) -> dict[str, Any]:
    profile = cargar_perfil(machine_id)
    errores = validar_valores_de_registro(profile, valores)
    if errores:
        raise ValoresInvalidos(errores)
    store = _cargar_store(profile)
    if index < 0 or index >= len(store.records):
        raise IndexError(f"No existe el registro {index}")
    antes = dict(store.records[index])
    clave_nombre = profile.campo_clave().nombre_interno
    clave_nueva = str(valores.get(clave_nombre, antes[clave_nombre])).strip()
    _verificar_clave_no_duplicada(profile, store, clave_nueva, exclude_index=index)
    store.update(index, valores)
    despues = dict(store.records[index])
    nuevo_hash = _guardar_con_backup(
        profile, store, [CambioRegistro("edicion", store.key_of(despues), antes, despues)],
        hash_esperado)
    return {"index": index, "registro": despues, "hash": nuevo_hash}


def eliminar_registro(machine_id: str, index: int,
                       hash_esperado: str | None = None) -> dict[str, Any]:
    profile = cargar_perfil(machine_id)
    store = _cargar_store(profile)
    if index < 0 or index >= len(store.records):
        raise IndexError(f"No existe el registro {index}")
    antes = dict(store.records[index])
    store.delete(index)
    nuevo_hash = _guardar_con_backup(
        profile, store, [CambioRegistro("baja", store.key_of(antes), antes, None)],
        hash_esperado)
    return {"hash": nuevo_hash}


def editar_en_masa(machine_id: str, indices: list[int], campo_nombre: str, texto: str,
                    hash_esperado: str | None = None) -> dict[str, Any]:
    """Aplica el mismo valor a un campo de varios registros de una sola vez,
    con la misma validación que la edición individual — el equivalente de
    `BulkEditDialog` (máquina232/src/app.py:2673). Se guarda como una sola
    operación (un backup) pero cada registro queda trazado por separado en
    el historial."""
    profile = cargar_perfil(machine_id)
    campo = profile.campo_por_nombre(campo_nombre)
    if campo is None or campo.es_clave or not campo.visible:
        raise ValoresInvalidos([_error_campo(campo_nombre,
            f"'{campo_nombre}' no es un parámetro editable de esta máquina.")])
    valor, error = parsear_valor_campo(campo, texto)
    if error:
        raise ValoresInvalidos([_error_campo(campo.titulo_ui, error)])

    store = _cargar_store(profile)
    indices_ordenados = sorted(set(indices))
    for i in indices_ordenados:
        if i < 0 or i >= len(store.records):
            raise IndexError(f"No existe el registro {i}")

    cambios = []
    for i in indices_ordenados:
        antes = dict(store.records[i])
        store.update(i, {campo.nombre_interno: valor})
        despues = dict(store.records[i])
        cambios.append(CambioRegistro("edicion", store.key_of(despues), antes, despues))

    nuevo_hash = _guardar_con_backup(profile, store, cambios, hash_esperado)
    return {"modificados": len(cambios), "hash": nuevo_hash}


def eliminar_en_masa(machine_id: str, indices: list[int],
                     hash_esperado: str | None = None) -> dict[str, Any]:
    """Baja de varios registros como una sola operación (un backup), con un
    evento de historial por registro — el equivalente de `_delete_indices`
    en el escritorio (máquina232/src/app.py:3806)."""
    profile = cargar_perfil(machine_id)
    store = _cargar_store(profile)
    # De mayor a menor índice: borrar corre una posición hacia atrás a los
    # que quedan después, así que hay que sacar primero los de más adelante.
    indices_ordenados = sorted(set(indices), reverse=True)
    for i in indices_ordenados:
        if i < 0 or i >= len(store.records):
            raise IndexError(f"No existe el registro {i}")

    cambios = []
    for i in indices_ordenados:
        antes = dict(store.records[i])
        store.delete(i)
        cambios.append(CambioRegistro("baja", store.key_of(antes), antes, None))

    nuevo_hash = _guardar_con_backup(profile, store, cambios, hash_esperado)
    return {"eliminados": len(cambios), "hash": nuevo_hash}


def _error_campo(titulo_ui: str, mensaje: str) -> ErrorValidacion:
    return ErrorValidacion(campo=titulo_ui, titulo_ui=titulo_ui, mensaje=mensaje)


def salud_maquina(machine_id: str) -> dict[str, Any]:
    profile = cargar_perfil(machine_id)
    store = _cargar_store_cacheado(profile)  # solo lectura
    _, _, meta = _rutas(profile)
    sidecar = Sidecar.load(meta)
    hallazgos = salud_mod.evaluar_salud(store, sidecar)
    return {
        "hallazgos": [dataclasses.asdict(h) for h in hallazgos],
        "slots_libres": salud_mod.contar_slots_libres(store),
    }


def listar_filtros(machine_id: str) -> list[dict[str, Any]]:
    profile = cargar_perfil(machine_id)
    data_dir = paths.data_dir_for(profile.id)
    return filtros_mod.cargar_guardados(data_dir)


def guardar_filtro(machine_id: str, nombre: str, busqueda: str,
                   rangos_crudos: list[str] | None = None) -> list[dict[str, Any]]:
    profile = cargar_perfil(machine_id)
    data_dir = paths.data_dir_for(profile.id)
    rangos = parsear_rangos(profile, rangos_crudos)
    return filtros_mod.agregar_o_reemplazar(data_dir, nombre, busqueda, rangos)


def eliminar_filtro(machine_id: str, nombre: str) -> list[dict[str, Any]]:
    profile = cargar_perfil(machine_id)
    data_dir = paths.data_dir_for(profile.id)
    return filtros_mod.eliminar(data_dir, nombre)
