import { Fragment, useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { api, type EventoHistorial } from "../api";
import Header from "../components/Header";

const ACCION_LABEL: Record<string, string> = {
  alta: "Alta",
  modificacion: "Modificación",
  baja: "Baja",
  importacion: "Importación",
  restauracion: "Restauración de backup",
  limpieza: "Limpieza",
};

export default function Historial() {
  const { id } = useParams<{ id: string }>();
  const [eventos, setEventos] = useState<EventoHistorial[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [expandido, setExpandido] = useState<number | null>(null);

  useEffect(() => {
    if (!id) return;
    api.listarHistorial(id).then(setEventos).catch((e) => setError(String(e)));
  }, [id]);

  return (
    <div className="pagina">
      <Header />
      <p className="breadcrumbs">
        <Link to="/">Máquinas</Link>
        <span className="sep">/</span>
        <Link to={`/maquinas/${id}`}>Máquina {id}</Link>
        <span className="sep">/</span>
        <strong>Historial</strong>
      </p>
      <h1>Historial de cambios</h1>
      <p className="muted">Tocá una fila para ver el detalle de qué cambió.</p>

      {error && <p className="error">{error}</p>}

      {!eventos ? (
        <p>Cargando…</p>
      ) : eventos.length === 0 ? (
        <div className="empty-state">Todavía no hay eventos.</div>
      ) : (
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>Fecha</th>
                <th>Usuario</th>
                <th>Acción</th>
                <th>Código</th>
                <th>Origen</th>
              </tr>
            </thead>
            <tbody>
              {eventos.map((e, i) => (
                <Fragment key={i}>
                  <tr onClick={() => setExpandido(expandido === i ? null : i)} style={{ cursor: "pointer" }}>
                    <td>{new Date(e.timestamp).toLocaleString()}</td>
                    <td>{e.usuario}</td>
                    <td>{ACCION_LABEL[e.accion] ?? e.accion}</td>
                    <td>{e.clave}</td>
                    <td className="muted">{e.origen}</td>
                  </tr>
                  {expandido === i && (
                    <tr>
                      <td colSpan={5} className="muted">
                        <strong>Antes:</strong> {e.anteriores ? JSON.stringify(e.anteriores) : "—"}
                        <br />
                        <strong>Después:</strong> {e.nuevos ? JSON.stringify(e.nuevos) : "—"}
                      </td>
                    </tr>
                  )}
                </Fragment>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
