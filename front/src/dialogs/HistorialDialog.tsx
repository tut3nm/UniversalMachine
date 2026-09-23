import { useEffect, useState } from "react";
import { ACCION_LABEL, api, type EventoHistorial, type FiltrosHistorial } from "../api";
import { Boton, Modal, useDialogos } from "../ui";

const OPCIONES_FECHA: { valor: number | undefined; etiqueta: string }[] = [
  { valor: undefined, etiqueta: "Todos" },
  { valor: 7, etiqueta: "Últimos 7 días" },
  { valor: 30, etiqueta: "Últimos 30 días" },
  { valor: 90, etiqueta: "Últimos 90 días" },
];

function detalleDe(e: EventoHistorial): string {
  return [
    `Fecha: ${new Date(e.timestamp).toLocaleString()}`,
    `Usuario: ${e.usuario}`,
    `Acción: ${ACCION_LABEL[e.accion] ?? e.accion}`,
    `Código: ${e.clave}`,
    `Origen: ${e.origen}`,
    "",
    "Valores anteriores:",
    e.anteriores ? JSON.stringify(e.anteriores, null, 2) : "(ninguno)",
    "",
    "Valores nuevos:",
    e.nuevos ? JSON.stringify(e.nuevos, null, 2) : "(ninguno)",
  ].join("\n");
}

/**
 * Historial de cambios con filtros por código, acción y antigüedad. Copia
 * `HistorialDialog` del escritorio: tabla de
 * 5 columnas, doble clic para el detalle, y accesos a Backups y a exportar
 * el informe en CSV.
 */
export default function HistorialDialog({
  machineId,
  onAbrirBackups,
  onCerrar,
}: {
  machineId: string;
  onAbrirBackups: () => void;
  onCerrar: () => void;
}) {
  const { avisar } = useDialogos();
  const [codigo, setCodigo] = useState("");
  const [accion, setAccion] = useState("");
  const [desde, setDesde] = useState<number | undefined>(undefined);
  const [eventos, setEventos] = useState<EventoHistorial[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [seleccionado, setSeleccionado] = useState<EventoHistorial | null>(null);

  const filtros: FiltrosHistorial = { codigo: codigo.trim() || undefined, accion: accion || undefined, desde };

  const cargarCon = (f: FiltrosHistorial) => {
    api
      .listarHistorial(machineId, f)
      .then((e) => {
        setEventos(e);
        setSeleccionado(null);
      })
      .catch((e) => setError(String(e)));
  };

  const cargar = () => cargarCon(filtros);

  // Carga inicial sin filtros; los filtros se vuelven a pedir explícitamente
  // con el botón "Filtrar", no en cada tecla tipeada en el código.
  useEffect(() => {
    api
      .listarHistorial(machineId, {})
      .then((e) => setEventos(e))
      .catch((e) => setError(String(e)));
  }, [machineId]);

  const verDetalle = async (e: EventoHistorial) => {
    await avisar({ titulo: `Detalle del evento — ${e.clave}`, mensaje: detalleDe(e) });
  };

  const onExportar = () => {
    if (!eventos || eventos.length === 0) {
      void avisar({ titulo: "Exportar informe", mensaje: "Nada para exportar." });
      return;
    }
    window.open(api.historialInformeCsvUrl(machineId, filtros), "_blank");
  };

  return (
    <Modal
      titulo="Historial de cambios"
      ancho={820}
      onCerrar={onCerrar}
      footer={
        <>
          <Boton tipo="outline-danger" onClick={onAbrirBackups}>
            🕐 Ver/restaurar backups…
          </Boton>
          <span className="ui-modal__footer-sep" />
          <Boton tipo="outline" onClick={onExportar}>
            Exportar informe (CSV)…
          </Boton>
          <Boton
            tipo="outline"
            disabled={!seleccionado}
            onClick={() => seleccionado && void verDetalle(seleccionado)}
          >
            Ver detalle
          </Boton>
          <Boton tipo="secondary" onClick={onCerrar}>
            Cerrar
          </Boton>
        </>
      }
    >
      {error && <p className="error">{error}</p>}

      <div className="hist-filtros">
        <label>
          Código
          <input
            value={codigo}
            onChange={(e) => setCodigo(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && cargar()}
          />
        </label>
        <label>
          Acción
          <select value={accion} onChange={(e) => setAccion(e.target.value)}>
            <option value="">Todas</option>
            {Object.entries(ACCION_LABEL).map(([valor, etiqueta]) => (
              <option key={valor} value={valor}>
                {etiqueta}
              </option>
            ))}
          </select>
        </label>
        <label>
          Fecha
          <select
            value={desde ?? ""}
            onChange={(e) => setDesde(e.target.value ? Number(e.target.value) : undefined)}
          >
            {OPCIONES_FECHA.map((o) => (
              <option key={o.etiqueta} value={o.valor ?? ""}>
                {o.etiqueta}
              </option>
            ))}
          </select>
        </label>
        <Boton tipo="outline" chico onClick={cargar}>
          Filtrar
        </Boton>
      </div>

      {!eventos ? (
        <p className="muted">Cargando…</p>
      ) : (
        <>
          <p className="hist-info">{eventos.length} evento(s) mostrados</p>
          {eventos.length === 0 ? (
            <p className="muted">No hay eventos que coincidan con el filtro.</p>
          ) : (
            <div className="table-wrap">
              <table>
                <thead>
                  <tr>
                    <th>Fecha</th>
                    <th>Acción</th>
                    <th>Código</th>
                    <th>Usuario</th>
                    <th>Origen</th>
                  </tr>
                </thead>
                <tbody>
                  {eventos.map((e, i) => (
                    <tr
                      key={`${e.timestamp}-${i}`}
                      className={
                        "tabla-fila-clic" + (seleccionado === e ? " fila-seleccionada" : "")
                      }
                      onClick={() => setSeleccionado(e)}
                      onDoubleClick={() => void verDetalle(e)}
                    >
                      <td>{new Date(e.timestamp).toLocaleString()}</td>
                      <td>{ACCION_LABEL[e.accion] ?? e.accion}</td>
                      <td>{e.clave}</td>
                      <td className="muted">{e.usuario}</td>
                      <td className="muted">{e.origen}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </>
      )}
    </Modal>
  );
}
