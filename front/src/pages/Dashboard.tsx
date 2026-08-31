import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api, type ResumenMaquina } from "../api";
import Header from "../components/Header";

function badgeSalud(alertas: number | null) {
  if (alertas === null) return null;
  if (alertas === 0) return <span className="badge badge-ok">Sin alertas</span>;
  return <span className="badge badge-warn">{alertas} alerta{alertas === 1 ? "" : "s"}</span>;
}

export default function Dashboard() {
  const [maquinas, setMaquinas] = useState<ResumenMaquina[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api.listarMaquinas().then(setMaquinas).catch((e) => setError(String(e)));
  }, []);

  return (
    <div>
      <Header />
      <h1>Máquinas</h1>
      <p className="muted">Elegí una máquina para ver y editar sus recetas.</p>

      {error && <p className="error">Error: {error}</p>}
      {!error && !maquinas && <p>Cargando…</p>}

      {maquinas && maquinas.length === 0 && (
        <div className="empty-state">Todavía no hay máquinas configuradas.</div>
      )}

      {maquinas && maquinas.length > 0 && (
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>Máquina</th>
                <th>Registros</th>
                <th>Salud</th>
                <th>Duplicados pendientes</th>
                <th>Última modificación</th>
              </tr>
            </thead>
            <tbody>
              {maquinas.map((m) => (
                <tr key={m.id} className={m.error ? "row-error" : ""}>
                  <td>
                    <Link to={`/maquinas/${m.id}`}>
                      <strong>{m.nombre}</strong>
                    </Link>
                  </td>
                  <td>{m.cantidad_registros ?? "—"}</td>
                  <td>{m.error ? <span className="badge badge-error">Error</span> : badgeSalud(m.alertas_salud)}</td>
                  <td>{m.duplicados_pendientes ?? "—"}</td>
                  <td className="muted">
                    {m.error ?? (m.ultima_modificacion ? new Date(m.ultima_modificacion).toLocaleString() : "—")}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
