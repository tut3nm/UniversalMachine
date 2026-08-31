import { Fragment, useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { api, type EventoHistorial } from "../api";

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

  if (error) return <p className="error">Error: {error}</p>;
  if (!id || !eventos) return <p>Cargando…</p>;

  return (
    <div>
      <p>
        <Link to={`/maquinas/${id}`}>← Máquina {id}</Link>
      </p>
      <h1>Historial — {id}</h1>
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
                <td>{e.origen}</td>
              </tr>
              {expandido === i && (
                <tr>
                  <td colSpan={5}>
                    <strong>Antes:</strong> {JSON.stringify(e.anteriores)}
                    <br />
                    <strong>Después:</strong> {JSON.stringify(e.nuevos)}
                  </td>
                </tr>
              )}
            </Fragment>
          ))}
        </tbody>
      </table>
      {eventos.length === 0 && <p>Todavía no hay eventos.</p>}
    </div>
  );
}
