import { useState } from "react";
import {
  api,
  type ArchivosAsistente,
  type PantallaAsistente,
  type ProgramaAsistente,
  type RespuestaAsistente,
  type TablaDetectada,
} from "../api";

function descargarBlob(blob: Blob, nombreArchivo: string) {
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = nombreArchivo;
  a.click();
  URL.revokeObjectURL(url);
}

/** Descripcion de cada operacion, armada por nuestro codigo a partir de la
 *  estructura: el modelo nunca redacta lo que el usuario lee
 *  (PLAN_ASISTENTE_IA.md, seccion 1: "la IA no escribe prosa"). */
function describir(op: ProgramaAsistente): string {
  const a = op.args as Record<string, unknown>;
  switch (op.op) {
    case "filtrar_filas":
      return `Solo las filas donde ${a.columna} es ${a.valor}`;
    case "expandir_por_catalogo": {
      const sufijos = (a.solo_sufijos as string[] | undefined) ?? [];
      return sufijos.length
        ? `Solo los sufijos ${sufijos.map((s) => `.${s}`).join(", ")}`
        : "Todas las variantes del catálogo de cada área";
    }
    case "reemplazar_campo":
      return `${a.campo} se llena con la columna ${a.columna}`;
    case "nombrar_archivo":
      return `Nombre de archivo: ${a.patron}`;
    case "agrupar_salida_por":
      return `Una carpeta por cada ${a.columna}`;
    case "quitar_comentarios":
      return "Sin las líneas de nota //";
    case "asignar_columna":
      return `La línea ${a.linea} se llena con la columna ${a.columna}`;
    case "nombre_archivo_desde":
      return `El nombre de cada archivo sale de la columna ${a.columna}`;
    default:
      return op.op;
  }
}

function Encabezado({ respuesta }: { respuesta: RespuestaAsistente }) {
  if (respuesta.ia_respondio === false) {
    return (
      <p className="muted">
        La IA local no respondió, así que no pude usar tu mensaje. Esto es lo que se hace sin
        indicaciones:
      </p>
    );
  }
  if (respuesta.sin_indicaciones) {
    return (
      <p className="muted">
        No encontré en tu mensaje indicaciones sobre los archivos de esta pantalla. Esto es lo que se
        hace sin indicaciones:
      </p>
    );
  }
  return null;
}

function Advertencias({ items }: { items?: string[] }) {
  if (!items || items.length === 0) return null;
  return (
    <ul className="plan-card__advertencias">
      {items.map((a, i) => (
        <li key={i}>{a}</li>
      ))}
    </ul>
  );
}

function BotonGenerar({
  respuesta,
  programa,
  archivos,
  texto,
  etiqueta,
  deshabilitado = false,
  alTerminar,
}: {
  respuesta: RespuestaAsistente;
  programa: ProgramaAsistente[];
  archivos: ArchivosAsistente;
  texto: string;
  etiqueta: string;
  deshabilitado?: boolean;
  /** Se llama despues de una generacion exitosa (ej. para ofrecer guardar
   *  el programa como formato en mediciones). */
  alTerminar?: () => void;
}) {
  const [ejecutando, setEjecutando] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [listo, setListo] = useState<string | null>(null);

  const onGenerar = async () => {
    setEjecutando(true);
    setError(null);
    try {
      const { blob, nombreArchivo } = await api.ejecutarAsistente(respuesta.pantalla, programa, archivos, texto);
      descargarBlob(blob, nombreArchivo);
      setListo(nombreArchivo);
      alTerminar?.();
    } catch (e) {
      setError(String(e));
    } finally {
      setEjecutando(false);
    }
  };

  return (
    <>
      {error && <p className="error">{error}</p>}
      {listo && <p className="badge badge-ok">Descargado: {listo}</p>}
      <button
        type="button"
        className="ui-btn ui-btn--primary ui-btn--sm"
        onClick={() => void onGenerar()}
        disabled={ejecutando || deshabilitado}
      >
        {ejecutando ? "Generando…" : etiqueta}
      </button>
    </>
  );
}

// -- mediciones: tarjeta editable ---------------------------------------------

interface TablaEditable {
  desde: number;
  hasta: number;
  tipo: "listado" | "tabla";
}

const SEPARADORES: { valor: string; nombre: string }[] = [
  { valor: ",", nombre: "coma" },
  { valor: ";", nombre: "punto y coma" },
  { valor: "\t", nombre: "tabulación" },
  { valor: "|", nombre: "barra |" },
];

function tablasDelPrograma(programa: ProgramaAsistente[]): TablaEditable[] {
  const op = programa.find((o) => o.op === "definir_tablas");
  return ((op?.args.tablas as TablaEditable[] | undefined) ?? []).map((t) => ({ ...t }));
}

function separadorDelPrograma(programa: ProgramaAsistente[]): string {
  const op = programa.find((o) => o.op === "usar_separador");
  return (op?.args.separador as string | undefined) ?? ",";
}

function armarPrograma(separador: string, tablas: TablaEditable[]): ProgramaAsistente[] {
  return [
    { op: "usar_separador", args: { separador } },
    { op: "definir_tablas", args: { tablas } },
  ];
}

function resumenTabla(t: TablaDetectada): string {
  const encabezado = t.con_encabezado ? `encabezado en la fila ${t.fila_encabezado}` : "sin encabezado";
  const columnas = t.columnas.join(", ") + (t.n_columnas > t.columnas.length ? "…" : "");
  return `${t.n_filas} fila(s) × ${t.n_columnas} columna(s), ${encabezado}. Columnas: ${columnas}`;
}

/** Dialogo de guardado tras generar (PLAN_MEMORIA_FORMATOS.md, seccion 4,
 *  paso 4): nombre editable, crea un formato nuevo o actualiza el
 *  reconocido si el usuario lo corrigio (`formatoId`). */
function GuardarFormato({
  pantalla,
  programa,
  archivos,
  texto,
  nombreSugerido,
  formatoId,
}: {
  pantalla: PantallaAsistente;
  programa: ProgramaAsistente[];
  archivos: ArchivosAsistente;
  texto: string;
  nombreSugerido: string;
  formatoId?: string;
}) {
  const [nombre, setNombre] = useState(nombreSugerido);
  const [guardando, setGuardando] = useState(false);
  const [guardado, setGuardado] = useState(false);
  const [error, setError] = useState<string | null>(null);

  if (guardado) {
    return <p className="badge badge-ok">Formato guardado: {nombre}</p>;
  }
  return (
    <div className="plan-card__guardar">
      <label>
        {formatoId ? "Actualizar formato" : "¿Lo guardo como…?"}{" "}
        <input type="text" value={nombre} onChange={(e) => setNombre(e.target.value)} />
      </label>
      <button
        type="button"
        className="ui-btn ui-btn--sm"
        disabled={guardando || !nombre.trim()}
        onClick={async () => {
          setGuardando(true);
          setError(null);
          try {
            await api.guardarFormatoAsistente(pantalla, nombre, programa, texto, archivos, formatoId);
            setGuardado(true);
          } catch (e) {
            setError(String(e));
          } finally {
            setGuardando(false);
          }
        }}
      >
        {guardando ? "Guardando…" : formatoId ? "Actualizar" : "Guardar formato"}
      </button>
      {error && <p className="error">{error}</p>}
    </div>
  );
}

function PlanMediciones({
  respuesta,
  texto,
  archivos,
}: {
  respuesta: RespuestaAsistente;
  texto: string;
  archivos: ArchivosAsistente;
}) {
  const [vista, setVista] = useState<RespuestaAsistente>(respuesta);
  const [separador, setSeparador] = useState(separadorDelPrograma(respuesta.programa));
  const [tablas, setTablas] = useState<TablaEditable[]>(tablasDelPrograma(respuesta.programa));
  const [editado, setEditado] = useState(false);
  const [actualizando, setActualizando] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [mostrarGuardar, setMostrarGuardar] = useState(false);

  // Si vino reconocido de la memoria y no se toco nada, ya esta guardado tal
  // cual: no hace falta preguntar. Si se corrigio, se ofrece actualizar ESE
  // formato en vez de crear uno nuevo.
  const vinoDeMemoria = respuesta.coincidencia === "unica" && Boolean(respuesta.formato);
  const yaGuardadoIntacto = vinoDeMemoria && !editado;

  const cambiarTabla = (i: number, cambio: Partial<TablaEditable>) => {
    setTablas((ts) => ts.map((t, j) => (j === i ? { ...t, ...cambio } : t)));
    setEditado(true);
  };

  const onActualizar = async () => {
    setActualizando(true);
    setError(null);
    try {
      const nueva = await api.previsualizarAsistente("mediciones", armarPrograma(separador, tablas), archivos);
      setVista(nueva);
      setEditado(false);
    } catch (e) {
      setError(String(e));
    } finally {
      setActualizando(false);
    }
  };

  const total = vista.total_lineas ?? respuesta.total_lineas ?? 1;

  return (
    <div className="plan-card">
      <Encabezado respuesta={respuesta} />
      <p className="plan-card__descripcion">
        {vista.tablas ? `El Excel va a tener ${vista.tablas.length} hoja(s):` : "Tablas del archivo:"}
      </p>

      <label className="plan-card__campo">
        Separador{" "}
        <select
          value={separador}
          onChange={(e) => {
            setSeparador(e.target.value);
            setEditado(true);
          }}
        >
          {SEPARADORES.map((s) => (
            <option key={s.nombre} value={s.valor}>
              {s.nombre}
            </option>
          ))}
        </select>
      </label>

      <ol className="plan-card__tablas">
        {tablas.map((t, i) => {
          const detectada = !editado ? vista.tablas?.[i] : undefined;
          return (
            <li key={i} className="plan-card__tabla">
              <strong>{detectada?.titulo ?? `Tabla ${i + 1}`}</strong>
              <div className="plan-card__tabla-campos">
                <label>
                  Filas{" "}
                  <input
                    type="number"
                    min={1}
                    max={total}
                    value={t.desde}
                    aria-label={`Tabla ${i + 1}: desde la fila`}
                    onChange={(e) => cambiarTabla(i, { desde: Number(e.target.value) })}
                  />
                </label>
                <label>
                  a{" "}
                  <input
                    type="number"
                    min={1}
                    max={total}
                    value={t.hasta}
                    aria-label={`Tabla ${i + 1}: hasta la fila`}
                    onChange={(e) => cambiarTabla(i, { hasta: Number(e.target.value) })}
                  />
                </label>
                <label>
                  Tipo{" "}
                  <select
                    value={t.tipo}
                    aria-label={`Tabla ${i + 1}: tipo`}
                    onChange={(e) => cambiarTabla(i, { tipo: e.target.value as TablaEditable["tipo"] })}
                  >
                    <option value="tabla">Tabla (con encabezado)</option>
                    <option value="listado">Listado (clave/valor)</option>
                  </select>
                </label>
                <button
                  type="button"
                  className="ui-btn ui-btn--sm"
                  aria-label={`Quitar la tabla ${i + 1}`}
                  onClick={() => {
                    setTablas((ts) => ts.filter((_, j) => j !== i));
                    setEditado(true);
                  }}
                >
                  Quitar
                </button>
              </div>
              {detectada && <p className="muted plan-card__tabla-resumen">{resumenTabla(detectada)}</p>}
            </li>
          );
        })}
      </ol>

      <button
        type="button"
        className="ui-btn ui-btn--sm"
        onClick={() => {
          setTablas((ts) => [...ts, { desde: 1, hasta: total, tipo: "tabla" }]);
          setEditado(true);
        }}
      >
        Agregar tabla
      </button>

      {!editado && <Advertencias items={vista.advertencias} />}
      {!editado && vista.error_validacion && <p className="error">{vista.error_validacion}</p>}
      {error && <p className="error">{error}</p>}

      {editado ? (
        <button
          type="button"
          className="ui-btn ui-btn--primary ui-btn--sm"
          onClick={() => void onActualizar()}
          disabled={actualizando || tablas.length === 0}
        >
          {actualizando ? "Actualizando…" : "Actualizar vista previa"}
        </button>
      ) : (
        <BotonGenerar
          respuesta={respuesta}
          programa={armarPrograma(separador, tablas)}
          archivos={archivos}
          texto={texto}
          etiqueta="Generar Excel"
          deshabilitado={Boolean(vista.error_validacion) || tablas.length === 0}
          alTerminar={yaGuardadoIntacto ? undefined : () => setMostrarGuardar(true)}
        />
      )}

      {mostrarGuardar && !yaGuardadoIntacto && (
        <GuardarFormato
          pantalla="mediciones"
          programa={armarPrograma(separador, tablas)}
          archivos={archivos}
          texto={texto}
          nombreSugerido={respuesta.formato?.nombre ?? (archivos.datos?.name.replace(/\.[^.]+$/, "") ?? "")}
          formatoId={vinoDeMemoria ? respuesta.formato?.id : undefined}
        />
      )}
    </div>
  );
}

// -- recetas por area y plantilla ---------------------------------------------

function PlanRecetas({
  respuesta,
  texto,
  archivos,
}: {
  respuesta: RespuestaAsistente;
  texto: string;
  archivos: ArchivosAsistente;
}) {
  const [mostrarGuardar, setMostrarGuardar] = useState(false);
  const yaGuardadoIntacto = respuesta.coincidencia === "unica" && Boolean(respuesta.formato);

  return (
    <div className="plan-card">
      <Encabezado respuesta={respuesta} />
      <ul className="plan-card__operaciones">
        {respuesta.programa.map((op, i) => (
          <li key={i}>{describir(op)}</li>
        ))}
      </ul>
      {respuesta.error_validacion ? (
        <p className="error">{respuesta.error_validacion}</p>
      ) : (
        <>
          <p className="plan-card__descripcion">Se van a generar {respuesta.cantidad_archivos ?? 0} archivo(s).</p>
          <Advertencias items={respuesta.advertencias} />
          <Advertencias items={respuesta.hallazgos?.map((h) => `${h.archivo}: ${h.mensaje}`)} />
          <BotonGenerar
            respuesta={respuesta}
            programa={respuesta.programa}
            archivos={archivos}
            texto={texto}
            etiqueta="Generar y descargar .zip"
            alTerminar={yaGuardadoIntacto ? undefined : () => setMostrarGuardar(true)}
          />
        </>
      )}

      {mostrarGuardar && !yaGuardadoIntacto && (
        <GuardarFormato
          pantalla="recetas_por_area"
          programa={respuesta.programa}
          archivos={archivos}
          texto={texto}
          nombreSugerido={archivos.listado?.name.replace(/\.[^.]+$/, "") ?? ""}
        />
      )}
    </div>
  );
}

function PlanPlantilla({
  respuesta,
  texto,
  archivos,
}: {
  respuesta: RespuestaAsistente;
  texto: string;
  archivos: ArchivosAsistente;
}) {
  const [mostrarGuardar, setMostrarGuardar] = useState(false);
  // Reconocido intacto de la memoria (no hay edicion en linea para
  // plantilla, a diferencia de mediciones): ya esta guardado, no hace falta
  // preguntar. Si el usuario describe otra cosa en el chat, esta respuesta
  // ya no trae `formato` y se ofrece guardar como nuevo.
  const yaGuardadoIntacto = respuesta.coincidencia === "unica" && Boolean(respuesta.formato);

  return (
    <div className="plan-card">
      <Encabezado respuesta={respuesta} />
      {respuesta.programa.length > 0 && (
        <ul className="plan-card__operaciones">
          {respuesta.programa.map((op, i) => (
            <li key={i}>{describir(op)}</li>
          ))}
        </ul>
      )}
      {respuesta.error_validacion ? (
        <p className="error">{respuesta.error_validacion}</p>
      ) : (
        <>
          <p className="plan-card__descripcion">Cómo se llena cada campo de la plantilla:</p>
          <ul className="plan-card__campos">
            {respuesta.campos?.map((c) => (
              <li key={c.linea}>
                <code>
                  {c.linea}: {c.texto}
                </code>{" "}
                ← {c.columna ? <strong>{c.columna}</strong> : <span className="muted">queda fijo</span>}
              </li>
            ))}
          </ul>
          <p className="muted">
            Nombre de cada archivo: columna <strong>{respuesta.columna_nombre_archivo}</strong>.
          </p>
          <p className="plan-card__descripcion">
            Se van a generar {respuesta.cantidad_archivos ?? 0} archivo(s)
            {respuesta.nombres_archivo?.length ? `, ej. ${respuesta.nombres_archivo.slice(0, 2).join(", ")}` : ""}.
          </p>
          <BotonGenerar
            respuesta={respuesta}
            programa={respuesta.programa}
            archivos={archivos}
            texto={texto}
            etiqueta="Generar y descargar .zip"
            alTerminar={yaGuardadoIntacto ? undefined : () => setMostrarGuardar(true)}
          />
        </>
      )}

      {mostrarGuardar && !yaGuardadoIntacto && (
        <GuardarFormato
          pantalla="plantilla"
          programa={respuesta.programa}
          archivos={archivos}
          texto={texto}
          nombreSugerido={archivos.plantilla?.name.replace(/\.[^.]+$/, "") ?? ""}
        />
      )}
    </div>
  );
}

export default function PlanCard({
  respuesta,
  texto,
  archivos,
}: {
  respuesta: RespuestaAsistente;
  texto: string;
  archivos: ArchivosAsistente;
}) {
  if (respuesta.faltan_archivos?.length) {
    return (
      <div className="plan-card">
        <p>
          Para trabajar necesito {respuesta.faltan_archivos.join(" y ")}:{" "}
          {respuesta.faltan_archivos.length > 1 ? "cargalos" : "cargalo"} en esta pantalla.
        </p>
      </div>
    );
  }
  if (respuesta.pantalla === "mediciones") {
    return <PlanMediciones respuesta={respuesta} texto={texto} archivos={archivos} />;
  }
  if (respuesta.pantalla === "plantilla") {
    return <PlanPlantilla respuesta={respuesta} texto={texto} archivos={archivos} />;
  }
  return <PlanRecetas respuesta={respuesta} texto={texto} archivos={archivos} />;
}
