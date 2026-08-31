import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api, type ResumenMaquina } from "../api";

export default function Dashboard() {
  const [maquinas, setMaquinas] = useState<ResumenMaquina[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api.listarMaquinas().then(setMaquinas).catch((e) => setError(String(e)));
  }, []);

  if (error) return <p className="error">Error: {error}</p>;
  if (!maquinas) return <p>Cargando…</p>;

  return (
    <div>
      <h1>Máquinas</h1>
      <table>
        <thead>
          <tr>
            <th>ID</th>
            <th>Nombre</th>
            <th>Registros</th>
            <th>Alertas de salud</th>
            <th>Duplicados pendientes</th>
            <th>Última modificación</th>
          </tr>
        </thead>
        <tbody>
          {maquinas.map((m) => (
            <tr key={m.id} className={m.error ? "row-error" : m.alertas_salud ? "row-warn" : ""}>
              <td>
                <Link to={`/maquinas/${m.id}`}>{m.id}</Link>
              </td>
              <td>{m.nombre}</td>
              <td>{m.cantidad_registros ?? "—"}</td>
              <td>{m.alertas_salud ?? "—"}</td>
              <td>{m.duplicados_pendientes ?? "—"}</td>
              <td>{m.ultima_modificacion ?? m.error ?? "—"}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
