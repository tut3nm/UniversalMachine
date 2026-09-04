import { useCallback, useEffect, useRef, useState } from "react";
import type { Campo, Registro } from "../api";

/** Alto de fila en píxeles. Tiene que coincidir con `--fila-alto` en ui.css:
 *  la virtualización calcula posiciones con este número. */
const ALTO_FILA = 34;
/** Filas de más que se renderizan arriba y abajo de lo visible, para que un
 *  scroll rápido no muestre huecos en blanco. */
const EXTRA = 8;

export interface Edicion {
  index: number;
  campo: string;
}

export interface Orden {
  col: string;
  desc: boolean;
}

interface Props {
  campos: Campo[];
  /** Cantidad de filas del conjunto filtrado (no de las cargadas). */
  totalFilas: number;
  /** Devuelve la fila en la posición n (0 en adelante) si ya se cargó. */
  filaEn: (n: number) => Registro | undefined;
  /** Cambia cada vez que llegan datos nuevos: fuerza el re-render. */
  version: number;
  asegurarRango: (desde: number, hasta: number) => void;
  orden: Orden | null;
  onOrdenar: (col: string) => void;
  seleccion: Set<number>;
  onClickFila: (e: React.MouseEvent, registro: Registro) => void;
  modoBorrado: boolean;
  edicion: Edicion | null;
  onEditarCelda: (registro: Registro, campo: Campo) => void;
  onGuardarCelda: (texto: string) => void;
  onCancelarCelda: () => void;
  onAbrirRegistro: (registro: Registro) => void;
}

/**
 * Tabla de registros virtualizada: solo renderiza las filas a la vista y
 * reserva el alto del resto con dos filas espaciadoras, para que el scroll
 * y la barra sigan representando el catálogo entero.
 *
 * De cara al operario se comporta igual que el Treeview del escritorio
 * (máquina232/src/app.py:3506): una sola lista continua, sin paginado,
 * ordenable por encabezado, con edición de una celda al doble clic.
 */
export default function TablaRegistros({
  campos,
  totalFilas,
  filaEn,
  version,
  asegurarRango,
  orden,
  onOrdenar,
  seleccion,
  onClickFila,
  modoBorrado,
  edicion,
  onEditarCelda,
  onGuardarCelda,
  onCancelarCelda,
  onAbrirRegistro,
}: Props) {
  const contRef = useRef<HTMLDivElement | null>(null);
  const [vista, setVista] = useState({ scrollTop: 0, alto: 480 });

  const medir = useCallback((el: HTMLDivElement | null) => {
    contRef.current = el;
    if (!el) return;
    setVista((v) =>
      v.alto === el.clientHeight && v.scrollTop === el.scrollTop
        ? v
        : { scrollTop: el.scrollTop, alto: el.clientHeight },
    );
  }, []);

  // El alto disponible cambia cuando aparece el pie de eliminación o cuando
  // se redimensiona la ventana: un observer lo sigue sin re-renderizar de más.
  useEffect(() => {
    const el = contRef.current;
    if (!el || typeof ResizeObserver === "undefined") return;
    const obs = new ResizeObserver(() =>
      setVista((v) => (v.alto === el.clientHeight ? v : { ...v, alto: el.clientHeight })),
    );
    obs.observe(el);
    return () => obs.disconnect();
  }, []);

  const visibles = Math.ceil(vista.alto / ALTO_FILA) + EXTRA * 2;
  // El scroll se recorta al alto real del contenido: si el conjunto se achica
  // (una baja, o un filtro que deja menos filas) la posición guardada puede
  // quedar más abajo del final, y sin este recorte no se dibujaría ninguna fila.
  const scrollMaximo = Math.max(0, totalFilas * ALTO_FILA - vista.alto);
  const scrollEfectivo = Math.min(vista.scrollTop, scrollMaximo);
  const desde = Math.max(0, Math.floor(scrollEfectivo / ALTO_FILA) - EXTRA);
  const hasta = Math.min(totalFilas, desde + visibles);

  useEffect(() => {
    if (totalFilas > 0) asegurarRango(desde, hasta);
  }, [desde, hasta, totalFilas, asegurarRango]);

  const nColumnas = campos.length + 1;
  const filas = [];
  for (let n = desde; n < hasta; n++) {
    const registro = filaEn(n);
    filas.push(
      <FilaRegistro
        key={n}
        n={n}
        registro={registro}
        campos={campos}
        nColumnas={nColumnas}
        seleccionada={registro ? seleccion.has(registro.index) : false}
        modoBorrado={modoBorrado}
        edicion={edicion}
        onClickFila={onClickFila}
        onEditarCelda={onEditarCelda}
        onGuardarCelda={onGuardarCelda}
        onCancelarCelda={onCancelarCelda}
        onAbrirRegistro={onAbrirRegistro}
      />,
    );
  }

  const flecha = (col: string) => (orden?.col === col ? (orden.desc ? " ▼" : " ▲") : "");

  return (
    <div
      className="mq__tabla-wrap"
      ref={medir}
      onScroll={(e) => {
        const el = e.currentTarget;
        setVista({ scrollTop: el.scrollTop, alto: el.clientHeight });
      }}
      data-version={version}
    >
      {/* El ancho mínimo mantiene legibles las columnas cuando hay muchas:
          si no entran, el contenedor scrollea en horizontal, igual que el
          Treeview del escritorio. */}
      <table
        className="mq__tabla"
        style={{ minWidth: 64 + campos.length * 144 }}
      >
        <thead>
          <tr>
            <th className="mq__col-pos" onClick={() => onOrdenar("pos")}>
              {modoBorrado ? "" : `#${flecha("pos")}`}
            </th>
            {campos.map((c) => (
              <th
                key={c.nombre_interno}
                className={c.rol === "clave" ? "mq__col-clave" : "mq__col-param"}
                onClick={() => onOrdenar(c.nombre_interno)}
                title={`Ordenar por ${c.titulo_ui}`}
              >
                {c.titulo_ui}
                {flecha(c.nombre_interno)}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {desde > 0 && (
            <tr className="mq__espaciador" aria-hidden="true">
              <td colSpan={nColumnas} style={{ height: desde * ALTO_FILA }} />
            </tr>
          )}
          {filas}
          {totalFilas - hasta > 0 && (
            <tr className="mq__espaciador" aria-hidden="true">
              <td colSpan={nColumnas} style={{ height: (totalFilas - hasta) * ALTO_FILA }} />
            </tr>
          )}
          {totalFilas === 0 && (
            <tr>
              <td className="muted" colSpan={nColumnas}>
                No hay registros que coincidan con la búsqueda.
              </td>
            </tr>
          )}
        </tbody>
      </table>
    </div>
  );
}

function FilaRegistro({
  n,
  registro,
  campos,
  nColumnas,
  seleccionada,
  modoBorrado,
  edicion,
  onClickFila,
  onEditarCelda,
  onGuardarCelda,
  onCancelarCelda,
  onAbrirRegistro,
}: {
  n: number;
  registro: Registro | undefined;
  campos: Campo[];
  nColumnas: number;
  seleccionada: boolean;
  modoBorrado: boolean;
  edicion: Edicion | null;
  onClickFila: (e: React.MouseEvent, registro: Registro) => void;
  onEditarCelda: (registro: Registro, campo: Campo) => void;
  onGuardarCelda: (texto: string) => void;
  onCancelarCelda: () => void;
  onAbrirRegistro: (registro: Registro) => void;
}) {
  // Fila todavía no traída del servidor: se dibuja vacía para que el alto
  // total no se mueva mientras llega la página.
  if (!registro) {
    return (
      <tr className="mq__fila-cargando">
        <td className="mq__col-pos">{n + 1}</td>
        <td colSpan={nColumnas - 1} />
      </tr>
    );
  }

  const clases = [
    registro.es_placeholder ? "mq__fila-placeholder" : "",
    seleccionada ? "mq__fila-marcada" : "",
  ]
    .filter(Boolean)
    .join(" ");

  return (
    <tr
      aria-selected={seleccionada}
      className={clases || undefined}
      onClick={(e) => onClickFila(e, registro)}
    >
      <td className="mq__col-pos">
        {modoBorrado ? (seleccionada ? "☑" : "☐") : registro.pos}
      </td>
      {campos.map((c) => {
        const editando =
          edicion?.index === registro.index && edicion.campo === c.nombre_interno;
        const valor = String(registro[c.nombre_interno] ?? "");
        return (
          <td
            key={c.nombre_interno}
            className={c.rol === "clave" ? "mq__col-clave" : "mq__col-param"}
            title={editando ? undefined : valor}
            onDoubleClick={() => {
              if (modoBorrado) return;
              // Igual que en el escritorio: la clave abre el diálogo entero
              // (puede afectar duplicados y metadatos), un parámetro se
              // edita en la celda.
              if (c.rol === "clave") onAbrirRegistro(registro);
              else onEditarCelda(registro, c);
            }}
          >
            {editando ? (
              <EditorCelda
                valorInicial={valor}
                onGuardar={onGuardarCelda}
                onCancelar={onCancelarCelda}
              />
            ) : (
              valor
            )}
          </td>
        );
      })}
    </tr>
  );
}

/** Input que reemplaza a la celda mientras se edita: Enter guarda, Escape
 *  cancela y perder el foco guarda, igual que `_editar_celda` del
 *  escritorio (máquina232/src/app.py:3710). */
function EditorCelda({
  valorInicial,
  onGuardar,
  onCancelar,
}: {
  valorInicial: string;
  onGuardar: (texto: string) => void;
  onCancelar: () => void;
}) {
  const [texto, setTexto] = useState(valorInicial);
  const cerrado = useRef(false);

  const cerrar = (guardar: boolean) => {
    if (cerrado.current) return;
    cerrado.current = true;
    if (guardar) onGuardar(texto);
    else onCancelar();
  };

  return (
    <input
      className="mq__editor-celda"
      autoFocus
      value={texto}
      onClick={(e) => e.stopPropagation()}
      onChange={(e) => setTexto(e.target.value)}
      onBlur={() => cerrar(true)}
      onKeyDown={(e) => {
        if (e.key === "Enter") {
          e.preventDefault();
          cerrar(true);
        } else if (e.key === "Escape") {
          e.preventDefault();
          cerrar(false);
        }
      }}
    />
  );
}
