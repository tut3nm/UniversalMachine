import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { api, type BackupInfo } from "../api";
import Header from "../components/Header";

export default function Backups() {
  const { id } = useParams<{ id: string }>();
  const [backups, setBackups] = useState<BackupInfo[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [mensaje, setMensaje] = useState<string | null>(null);

  const cargar = () => {
    if (!id) return;
    api
      .listarBackups(id)
      .then((b) => setBackups([...b].reverse()))
      .catch((e) => setError(String(e)));
  };

  useEffect(cargar, [id]);

  const onRestaurar = async (nombre: string, fechaLegible: string) => {
    if (!id) return;
    if (
      !confirm(
        `¿Restaurar el backup del ${fechaLegible}? Esto reemplaza el archivo actual (se guarda un backup del estado actual antes).`,
      )
    )
      return;
    try {
      await api.restaurarBackup(id, nombre);
      setMensaje("Backup restaurado correctamente.");
      cargar();
    } catch (e) {
      setError(String(e));
    }
  };

  return (
    <div className="pagina">
      <Header />
      <p className="breadcrumbs">
        <Link to="/">Máquinas</Link>
        <span className="sep">/</span>
        <Link to={`/maquinas/${id}`}>Máquina {id}</Link>
        <span className="sep">/</span>
        <strong>Backups</strong>
      </p>
      <h1>Backups</h1>
      <p className="muted">Se crea uno automáticamente antes de cada guardado.</p>

      {error && <p className="error">{error}</p>}
      {mensaje && <p className="badge badge-ok">{mensaje}</p>}

      {!backups ? (
        <p>Cargando…</p>
      ) : backups.length === 0 ? (
        <div className="empty-state">Todavía no hay backups.</div>
      ) : (
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>Fecha</th>
                <th>Tamaño</th>
                <th></th>
              </tr>
            </thead>
            <tbody>
              {backups.map((b) => (
                <tr key={b.nombre}>
                  <td>{new Date(b.timestamp).toLocaleString()}</td>
                  <td className="muted">{(b.tamano_bytes / 1024).toFixed(1)} KB</td>
                  <td>
                    <button
                      className="btn-secondary btn-small"
                      onClick={() => onRestaurar(b.nombre, new Date(b.timestamp).toLocaleString())}
                    >
                      Restaurar este backup
                    </button>
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
