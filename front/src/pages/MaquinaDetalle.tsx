import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import {
  api,
  esNumerico,
  FILTROS_VACIOS,
  type Campo,
  type DetalleMaquina,
  type FiltrosTabla,
  type InfoApp,
  type Registro,
  type RespuestaSalud,
} from "../api";
import TablaRegistros, { type Edicion, type Orden } from "../components/TablaRegistros";
import BulkEditDialog from "../dialogs/BulkEditDialog";
import FiltrosDialog from "../dialogs/FiltrosDialog";
import RegistroDialog from "../dialogs/RegistroDialog";
import SaludDialog from "../dialogs/SaludDialog";
import { useAtajos } from "../hooks/useAtajos";
import { claveDeFiltros, useCatalogo } from "../hooks/useCatalogo";
import {
  BarraEstado,
  Boton,
  MenuDesplegable,
  Separador,
  useDialogos,
  useToast,
  type TonoEstado,
} from "../ui";
import { parsearValorCampo } from "../validacion";

/** Se muestra en el tooltip de lo que todavía no está portado a la web. */
const PENDIENTE = " — todavía no disponible en la versión web";

/** Espera antes de mandar la búsqueda al servidor, para no pedir una
 *  consulta por cada tecla mientras el operario escribe un código. */
const ESPERA_BUSQUEDA_MS = 250;

interface Estado {
  mensaje: string;
  tono: TonoEstado;
}

/**
 * Pantalla principal de una máquina: header, toolbar, tabla y barra de
 * estado, con la misma distribución que la ventana del escritorio
 * (máquina232/src/app.py:3366, `App._build_ui`).
 */
export default function MaquinaDetalle() {
  const { id } = useParams<{ id: string }>();
  if (!id) return null;
  // `key` fuerza un montaje limpio al cambiar de máquina: la búsqueda, el
  // orden, la selección y el modo eliminación no deben cruzarse entre
  // máquinas, igual que en el escritorio, donde `_activate_profile`
  // reconstruye la ventana entera.
  return <VistaMaquina key={id} id={id} />;
}

function VistaMaquina({ id }: { id: string }) {
  const navigate = useNavigate();
  const toast = useToast();
  const { confirmar, avisar } = useDialogos();

  const [detalle, setDetalle] = useState<DetalleMaquina | null>(null);
  const [info, setInfo] = useState<InfoApp | null>(null);
  const [cantidadMaquinas, setCantidadMaquinas] = useState(0);
  const [errorCarga, setErrorCarga] = useState<string | null>(null);

  // Lo que se tipea (inmediato) y lo que se le pide al servidor (con espera).
  const [busqueda, setBusqueda] = useState("");
  const [busquedaAplicada, setBusquedaAplicada] = useState("");
  const [mostrarSlots, setMostrarSlots] = useState(false);
  const [orden, setOrden] = useState<Orden | null>(null);
  const [rangosAplicados, setRangosAplicados] = useState<string[]>([]);

  const [seleccion, setSeleccion] = useState<Set<number>>(new Set());
  const [modoBorrado, setModoBorrado] = useState(false);
  const [edicion, setEdicion] = useState<Edicion | null>(null);
  const [dialogoRegistro, setDialogoRegistro] = useState<
    { modo: "alta" } | { modo: "edicion"; registro: Registro } | null
  >(null);
  const [dialogoBulkEdit, setDialogoBulkEdit] = useState(false);
  const [dialogoFiltros, setDialogoFiltros] = useState(false);
  const [dialogoSalud, setDialogoSalud] = useState<RespuestaSalud | null>(null);

  const [estado, setEstado] = useState<Estado>({ mensaje: "", tono: "normal" });
  const buscadorRef = useRef<HTMLInputElement>(null);
  const ultimaFilaRef = useRef<number | null>(null);

  const filtros: FiltrosTabla = useMemo(
    () => ({
      ...FILTROS_VACIOS,
      q: busquedaAplicada,
      rangos: rangosAplicados,
      placeholders: mostrarSlots,
      orden: orden?.col ?? null,
      dir: orden?.desc ? "desc" : "asc",
    }),
    [busquedaAplicada, rangosAplicados, mostrarSlots, orden],
  );

  const catalogo = useCatalogo(id, filtros);

  const decir = useCallback(
    (mensaje: string, tono: TonoEstado = "normal") => setEstado({ mensaje, tono }),
    [],
  );

  useEffect(() => {
    const t = window.setTimeout(() => setBusquedaAplicada(busqueda), ESPERA_BUSQUEDA_MS);
    return () => window.clearTimeout(t);
  }, [busqueda]);

  useEffect(() => {
    let vivo = true;
    api
      .obtenerMaquina(id)
      .then((m) => vivo && setDetalle(m))
      .catch((e) => vivo && setErrorCarga(String(e)));
    api.info().then((i) => vivo && setInfo(i)).catch(() => {});
    api
      .listarMaquinas()
      .then((ms) => vivo && setCantidadMaquinas(ms.length))
      .catch(() => {});
    return () => {
      vivo = false;
    };
  }, [id]);

  // Las advertencias de carga (celdas con datos más allá del último registro
  // reconocido) se avisan una sola vez, como en `_avisar_si_columnas_fantasma`.
  const advertidoRef = useRef(false);
  useEffect(() => {
    if (advertidoRef.current || catalogo.advertencias.length === 0) return;
    advertidoRef.current = true;
    void avisar({
      titulo: "Posibles datos no cargados",
      tipo: "aviso",
      mensaje:
        "Se detectaron celdas con datos que NO se cargaron porque están más " +
        "allá del último registro reconocido en el archivo:\n\n" +
        catalogo.advertencias.join("\n\n"),
    });
  }, [catalogo.advertencias, avisar]);

  const campos: Campo[] = useMemo(() => detalle?.campos ?? [], [detalle]);
  const campoClave = campos.find((c) => c.rol === "clave");
  const parametros = useMemo(() => campos.filter((c) => c.rol === "parametro"), [campos]);
  const parametrosNumericos = useMemo(
    () => parametros.filter(esNumerico),
    [parametros],
  );
  const hayNumericos = parametrosNumericos.length > 0;
  const hayParametros = parametros.length > 0;

  const claveDe = useCallback(
    (r: Registro) => String(r[campoClave?.nombre_interno ?? ""] ?? ""),
    [campoClave],
  );

  const registroSeleccionadoUnico = (): Registro | null => {
    if (seleccion.size !== 1) return null;
    return catalogo.filaPorIndice([...seleccion][0]) ?? null;
  };

  // -- orden y filtros ------------------------------------------------------
  const onOrdenar = (col: string) => {
    if (modoBorrado) return;
    setOrden((o) => (o && o.col === col ? { col, desc: !o.desc } : { col, desc: false }));
  };

  // -- selección ------------------------------------------------------------
  const alternar = (index: number) =>
    setSeleccion((s) => {
      const nueva = new Set(s);
      if (nueva.has(index)) nueva.delete(index);
      else nueva.add(index);
      return nueva;
    });

  /** Shift+clic marca todo lo que hay entre la última fila tocada y esta.
   *  El rango se pide al servidor porque puede abarcar filas que la tabla
   *  virtualizada todavía no bajó. */
  const seleccionarRango = async (hastaPos: number) => {
    const desdePos = ultimaFilaRef.current ?? hastaPos;
    const a = Math.min(desdePos, hastaPos);
    const b = Math.max(desdePos, hastaPos);
    try {
      const { indices } = await api.indicesFiltrados(id, filtros);
      setSeleccion((s) => new Set([...s, ...indices.slice(a - 1, b)]));
    } catch (e) {
      setEstado({ mensaje: String(e), tono: "error" });
    }
  };

  const onClickFila = (e: React.MouseEvent, registro: Registro) => {
    if (modoBorrado) {
      alternar(registro.index);
      ultimaFilaRef.current = registro.pos;
      return;
    }
    if (e.shiftKey && ultimaFilaRef.current !== null) {
      void seleccionarRango(registro.pos);
      return;
    }
    if (e.ctrlKey || e.metaKey) alternar(registro.index);
    else setSeleccion(new Set([registro.index]));
    ultimaFilaRef.current = registro.pos;
  };

  const seleccionarTodoLoFiltrado = async () => {
    try {
      const { indices } = await api.indicesFiltrados(id, filtros);
      setSeleccion(new Set(indices));
    } catch (e) {
      setEstado({ mensaje: String(e), tono: "error" });
    }
  };

  // -- acciones -------------------------------------------------------------
  const trasGuardar = (mensaje: string) => {
    decir("Cambios guardados");
    toast.mostrar(mensaje);
    catalogo.recargar();
  };

  const reportarFallo = async (e: unknown, titulo: string) => {
    decir("⚠ Cambios SIN guardar — no subas este archivo a la máquina", "error");
    await avisar({ titulo, mensaje: String(e), tipo: "error" });
  };

  const onNuevo = () => {
    if (modoBorrado) return;
    setDialogoRegistro({ modo: "alta" });
  };

  const onEditar = async () => {
    if (modoBorrado) return;
    const reg = registroSeleccionadoUnico();
    if (!reg) {
      await avisar({ titulo: "Editar", mensaje: "Seleccioná un registro para editar." });
      return;
    }
    setDialogoRegistro({ modo: "edicion", registro: reg });
  };

  /** Devuelve un mensaje si falla (el diálogo se queda abierto para
   *  corregir: clave duplicada, valor fuera de rango, conflicto de
   *  guardado) o nada si tuvo éxito (el diálogo se cierra solo, porque
   *  `dialogoRegistro` pasa a null). */
  const guardarRegistro = async (valores: Record<string, unknown>): Promise<string | void> => {
    if (!dialogoRegistro) return;
    try {
      const r =
        dialogoRegistro.modo === "alta"
          ? await api.crearRegistro(id, valores, catalogo.hash)
          : await api.actualizarRegistro(
              id,
              dialogoRegistro.registro.index,
              valores,
              catalogo.hash,
            );
      setDialogoRegistro(null);
      trasGuardar(
        dialogoRegistro.modo === "alta"
          ? `Registro «${claveDe(r.registro)}» agregado.`
          : `Registro «${claveDe(r.registro)}» modificado.`,
      );
    } catch (e) {
      return String(e);
    }
  };

  // -- edición en línea de una celda ----------------------------------------
  const onEditarCelda = (registro: Registro, campo: Campo) => {
    setSeleccion(new Set([registro.index]));
    setEdicion({ index: registro.index, campo: campo.nombre_interno });
  };

  const onGuardarCelda = async (texto: string) => {
    const actual = edicion;
    setEdicion(null);
    if (!actual) return;
    const campo = campos.find((c) => c.nombre_interno === actual.campo);
    if (!campo) return;
    const fila = catalogo.filaPorIndice(actual.index);
    if (fila && String(fila[campo.nombre_interno] ?? "").trim() === texto.trim()) return;

    const parseo = parsearValorCampo(campo, texto);
    if (parseo.error) {
      await avisar({ titulo: "No se guardó el cambio", mensaje: parseo.error, tipo: "aviso" });
      return;
    }
    try {
      await api.actualizarRegistro(
        id,
        actual.index,
        { [campo.nombre_interno]: parseo.valor },
        catalogo.hash,
      );
      decir("Cambios guardados");
      catalogo.recargar();
    } catch (e) {
      await reportarFallo(e, "No se pudo guardar el cambio");
    }
  };

  // -- edición en masa --------------------------------------------------------
  const onBulkEdit = async () => {
    if (modoBorrado) return;
    if (seleccion.size < 2) {
      await avisar({
        titulo: "Editar en masa",
        mensaje:
          "Seleccioná dos o más registros (Ctrl+clic o Shift+clic) para " +
          "aplicarles el mismo valor de una vez. Para uno solo, usá " +
          "«Editar» o doble clic en la celda.",
      });
      return;
    }
    setDialogoBulkEdit(true);
  };

  const bulkEditAplicar = async (campo: Campo, texto: string): Promise<string | void> => {
    try {
      const r = await api.editarEnMasa(id, [...seleccion], campo.nombre_interno, texto,
        catalogo.hash);
      catalogo.setHash(r.hash);
      setDialogoBulkEdit(false);
      setSeleccion(new Set());
      trasGuardar(`${r.modificados} registro(s) actualizados.`);
    } catch (e) {
      return String(e);
    }
  };

  // -- salud del catálogo ------------------------------------------------------
  const onSalud = async () => {
    try {
      setDialogoSalud(await api.salud(id));
    } catch (e) {
      decir(String(e), "error");
    }
  };

  /** Busca el código en la tabla, igual que `ir_a_registro` del escritorio
   *  (máquina232/src/app.py:3640): limpia los filtros que lo puedan estar
   *  ocultando y lo deja como resultado único de la búsqueda. Los hallazgos
   *  de salud son siempre sobre registros reales, así que no hace falta
   *  activar el toggle de slots vacíos. */
  const irARegistroDesdeSalud = (code: string) => {
    setDialogoSalud(null);
    setRangosAplicados([]);
    setBusqueda(code);
    setBusquedaAplicada(code);
  };

  // -- filtros avanzados --------------------------------------------------------
  const aplicarFiltrosRangos = (rangos: string[]) => setRangosAplicados(rangos);

  const aplicarPreset = (busquedaPreset: string, rangos: string[]) => {
    setBusqueda(busquedaPreset);
    setBusquedaAplicada(busquedaPreset);
    setRangosAplicados(rangos);
  };

  // -- bajas ----------------------------------------------------------------
  const borrarIndices = async (indices: number[]) => {
    if (indices.length === 0) return;
    const codigos = indices
      .map((i) => {
        const r = catalogo.filaPorIndice(i);
        return r ? claveDe(r) : `#${i + 1}`;
      })
      .slice(0, 5);
    const preview = codigos.join(", ") + (indices.length > 5 ? " …" : "");
    const ok = await confirmar({
      titulo: "Confirmar eliminación",
      mensaje: `¿Eliminar ${indices.length} registro(s)?\n\n${preview}`,
      peligro: true,
      textoOk: "Eliminar",
      textoCancelar: "Cancelar",
    });
    if (!ok) return;
    try {
      const r = await api.eliminarEnMasa(id, indices, catalogo.hash);
      catalogo.setHash(r.hash);
      setSeleccion(new Set());
      decir("Cambios guardados");
      toast.mostrar(`${r.eliminados} registro(s) eliminado(s).`, "aviso");
      catalogo.recargar();
    } catch (e) {
      await reportarFallo(e, "No se pudieron eliminar los registros");
      catalogo.recargar();
    }
  };

  const onEliminarInmediato = async () => {
    if (modoBorrado) return;
    if (seleccion.size === 0) {
      await avisar({ titulo: "Eliminar", mensaje: "Seleccioná uno o más registros." });
      return;
    }
    await borrarIndices([...seleccion]);
  };

  const entrarModoBorrado = () => {
    setSeleccion(new Set());
    setEdicion(null);
    setModoBorrado(true);
  };

  const salirModoBorrado = () => {
    setModoBorrado(false);
    setSeleccion(new Set());
  };

  const confirmarBorradoSeleccion = async () => {
    if (seleccion.size === 0) {
      await avisar({ titulo: "Eliminar", mensaje: "Seleccioná uno o más registros." });
      return;
    }
    const indices = [...seleccion];
    setModoBorrado(false);
    await borrarIndices(indices);
  };

  const onAcercaDe = () =>
    avisar({
      titulo: "Acerca de",
      mensaje: [
        info?.titulo ?? "Configurador de Parámetros de Planta",
        "",
        `Versión: ${info?.version ?? "—"}`,
        `Compilación: ${info?.compilacion ?? "—"}`,
        `Máquina activa: ${detalle?.nombre ?? ""}`,
        "",
        `Registro de diagnóstico: ${info?.log_dir ?? "—"}`,
      ].join("\n"),
    });

  // -- atajos ---------------------------------------------------------------
  useAtajos(
    {
      "ctrl+n": onNuevo,
      "ctrl+f": () => buscadorRef.current?.focus(),
      "ctrl+z": () => decir("Nada para deshacer"),
      "ctrl+y": () => decir("Nada para rehacer"),
      Delete: () => void onEliminarInmediato(),
      Enter: () => void onEditar(),
      Escape: () => modoBorrado && salirModoBorrado(),
    },
    !!detalle && !dialogoRegistro && !edicion,
  );

  // -- render ---------------------------------------------------------------
  if (errorCarga) {
    return (
      <div className="mq">
        <div className="mq__centro">
          <p className="error">{errorCarga}</p>
          <Boton tipo="secondary" onClick={() => navigate("/")}>
            Volver a las máquinas
          </Boton>
        </div>
      </div>
    );
  }

  if (!detalle) {
    return (
      <div className="mq">
        <div className="mq__centro">Cargando…</div>
      </div>
    );
  }

  const { mostrados, reales, total } = catalogo.totales;
  const cuenta = detalle.tiene_placeholders
    ? `${mostrados} mostrados · ${reales} reales · ${total} slots`
    : `${mostrados} mostrados · ${total} registros`;

  return (
    <div className="mq">
      <header className="mq__header">
        <h1 className="mq__titulo">{detalle.nombre}</h1>
        {detalle.descripcion && (
          <span className="mq__descripcion">{detalle.descripcion}</span>
        )}
        <div className="mq__header-acciones">
          {cantidadMaquinas >= 3 && (
            <Boton
              tipo="light"
              chico
              onClick={() => navigate("/")}
              tooltip="Vista consolidada de todas las máquinas: última modificación, registros, duplicados y alertas de salud"
            >
              📊 Panel
            </Boton>
          )}
          <Boton
            tipo="light"
            chico
            onClick={() => navigate("/")}
            tooltip="Ver y elegir entre los documentos de configuración de todas las máquinas"
          >
            🗂 Máquinas
          </Boton>
        </div>
      </header>

      <div className="mq__toolbar">
        <div className="mq__toolbar-izq">
          <div className="mq__buscador">
            <span className="mq__buscador-icono">🔍</span>
            <input
              ref={buscadorRef}
              value={busqueda}
              disabled={modoBorrado}
              placeholder="Buscar"
              aria-label="Buscar por cualquier dato"
              onChange={(e) => setBusqueda(e.target.value)}
            />
            <span className="mq__buscador-ayuda">Buscar por cualquier dato</span>
          </div>

          {hayNumericos && (
            <Boton
              tipo="ghost"
              chico
              onClick={() => setDialogoFiltros(true)}
              disabled={modoBorrado}
              tooltip="Filtrar por rango numérico, y guardar combinaciones frecuentes de búsqueda + filtros"
            >
              ▾ Filtros
            </Boton>
          )}

          <Separador />

          <Boton
            tipo="primary"
            onClick={onNuevo}
            disabled={modoBorrado}
            tooltip="Agregar un registro nuevo al final (Ctrl+N)"
          >
            ＋ Nuevo
          </Boton>
          <Boton
            tipo="outline"
            onClick={() => void onEditar()}
            disabled={modoBorrado}
            tooltip="Modificar el registro seleccionado (doble clic)"
          >
            ✎ Editar
          </Boton>
          <Boton
            tipo="danger"
            onClick={entrarModoBorrado}
            disabled={modoBorrado}
            tooltip="Seleccionar uno o más registros para eliminar"
          >
            🗑 Eliminar
          </Boton>
          {hayParametros && (
            <Boton
              tipo="outline"
              onClick={() => void onBulkEdit()}
              disabled={modoBorrado}
              tooltip="Aplicar un mismo valor a todos los registros seleccionados (Ctrl+clic o Shift+clic para elegir varios)"
            >
              ✎✎ Editar en masa
            </Boton>
          )}

          <Separador />

          <Boton
            tipo="ghost"
            chico
            disabled
            tooltip={"Deshacer el último cambio (Ctrl+Z)" + PENDIENTE}
          >
            ↶
          </Boton>
          <Boton tipo="ghost" chico disabled tooltip={"Rehacer (Ctrl+Y)" + PENDIENTE}>
            ↷
          </Boton>

          {detalle.tiene_duplicados && (
            <>
              <Separador />
              <Boton
                tipo="secondary"
                disabled
                tooltip={
                  "Revisar códigos parecidos y decidir cuáles son duplicados reales" +
                  PENDIENTE
                }
              >
                ⧉ Duplicados
              </Boton>
            </>
          )}

          <Separador />

          <Boton
            tipo="secondary"
            disabled
            tooltip={
              "Comparar contra un Excel y aplicar solo los cambios que elijas" + PENDIENTE
            }
          >
            📥 Importar
          </Boton>
        </div>

        <div className="mq__toolbar-der">
          <Boton
            tipo="outline"
            onClick={() => void onSalud()}
            disabled={modoBorrado}
            tooltip="Ver de una pasada: valores fuera de rango, duplicados sin revisar, campos vacíos y slots libres"
          >
            ❤ Salud
          </Boton>
          <Boton
            tipo="outline"
            disabled
            tooltip={
              "Comparar el archivo actual contra el original, campo por campo" + PENDIENTE
            }
          >
            🔍 Ver cambios
          </Boton>
          <Boton
            tipo="outline"
            onClick={() => navigate(`/maquinas/${id}/historial`)}
            disabled={modoBorrado}
            tooltip="Ver qué cambió, cuándo y quién lo hizo"
          >
            📜 Historial
          </Boton>
          <Boton
            tipo="outline"
            onClick={() => navigate(`/maquinas/${id}/backups`)}
            disabled={modoBorrado}
            tooltip="Ver puntos de respaldo automáticos y restaurar uno en particular"
          >
            🕐 Backups
          </Boton>
          <Boton
            tipo="outline-danger"
            disabled
            tooltip={"Descartar todos los cambios y volver al archivo original" + PENDIENTE}
          >
            ⟲ Restaurar
          </Boton>
          <MenuDesplegable
            etiqueta="📤 Exportar ▾"
            disabled
            tooltip={"Guardar una copia del archivo en cualquier carpeta de la PC" + PENDIENTE}
            items={[
              { etiqueta: "Exportar archivo actual (con cambios)…", onSelect: () => {} },
              { etiqueta: "Exportar archivo original (sin cambios)…", onSelect: () => {} },
            ]}
          />
        </div>
      </div>

      {detalle.tiene_placeholders && (
        <label className="mq__toggle">
          <input
            type="checkbox"
            checked={mostrarSlots}
            disabled={modoBorrado}
            onChange={(e) => setMostrarSlots(e.target.checked)}
          />
          Mostrar slots vacíos
        </label>
      )}

      {/* Remontar la tabla al cambiar el filtro o el orden deja el scroll
          arriba, como cuando el escritorio reconstruye el Treeview: si no,
          una búsqueda que deja 3 resultados heredaría la posición anterior. */}
      <TablaRegistros
        key={claveDeFiltros(filtros)}
        campos={campos}
        totalFilas={catalogo.totales.mostrados}
        filaEn={catalogo.filaEn}
        version={catalogo.version}
        asegurarRango={catalogo.asegurarRango}
        orden={orden}
        onOrdenar={onOrdenar}
        seleccion={seleccion}
        onClickFila={onClickFila}
        modoBorrado={modoBorrado}
        edicion={edicion}
        onEditarCelda={onEditarCelda}
        onGuardarCelda={(t) => void onGuardarCelda(t)}
        onCancelarCelda={() => setEdicion(null)}
        onAbrirRegistro={(r) => setDialogoRegistro({ modo: "edicion", registro: r })}
      />

      {modoBorrado && (
        <div className="mq__pie-borrado">
          <span>
            {seleccion.size
              ? `${seleccion.size} registro(s) seleccionado(s)`
              : "Marcá los registros a eliminar (tocá la fila)."}
          </span>
          <Boton
            tipo="outline"
            chico
            onClick={() => void seleccionarTodoLoFiltrado()}
            tooltip="Marcar los registros que hoy se ven con la búsqueda y los filtros aplicados"
          >
            Seleccionar todo lo filtrado
          </Boton>
          <Boton tipo="secondary" onClick={salirModoBorrado}>
            Cancelar
          </Boton>
          <Boton tipo="danger" onClick={() => void confirmarBorradoSeleccion()}>
            Aceptar
          </Boton>
        </div>
      )}

      <BarraEstado
        mensaje={catalogo.error ?? estado.mensaje}
        tono={catalogo.error ? "error" : estado.tono}
        cuenta={catalogo.listo ? cuenta : "cargando…"}
        version={info?.version}
        onAcercaDe={() => void onAcercaDe()}
      />

      {dialogoRegistro && (
        <RegistroDialog
          titulo={dialogoRegistro.modo === "alta" ? "Nuevo registro" : "Modificar registro"}
          campos={campos}
          registro={dialogoRegistro.modo === "edicion" ? dialogoRegistro.registro : null}
          onGuardar={guardarRegistro}
          onCerrar={() => setDialogoRegistro(null)}
        />
      )}

      {dialogoBulkEdit && (
        <BulkEditDialog
          campos={parametros}
          cantidad={seleccion.size}
          onAplicar={bulkEditAplicar}
          onCerrar={() => setDialogoBulkEdit(false)}
        />
      )}

      {dialogoSalud && (
        <SaludDialog
          hallazgos={dialogoSalud.hallazgos}
          slotsLibres={dialogoSalud.slots_libres}
          onIrAlRegistro={irARegistroDesdeSalud}
          onCerrar={() => setDialogoSalud(null)}
        />
      )}

      {dialogoFiltros && (
        <FiltrosDialog
          machineId={id}
          campos={parametrosNumericos}
          rangosActuales={rangosAplicados}
          busquedaActual={busqueda}
          onAplicar={aplicarFiltrosRangos}
          onAplicarPreset={aplicarPreset}
          onCerrar={() => setDialogoFiltros(false)}
        />
      )}
    </div>
  );
}
