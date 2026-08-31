import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { api, type BackupInfo } from "../api";

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

  const onRestaurar = async (nombre: string) => {
    if (!id) return;
    if (!confirm(`¿Restaurar el backup "${nombre}"? Esto reemplaza el archivo actual (se guarda un backup del estado actual antes).`))
      return;
    try {
      await api.restaurarBackup(id, nombre);
      setMensaje(`Restaurado: ${nombre}`);
      cargar();
    } catch (e) {
      setError(String(e));
    }
  };

  if (error) return <p className="error">Error: {error}</p>;
  if (!id || !backups) return <p>Cargando…</p>;

  return (
    <div>
      <p>
        <Link to={`/maquinas/${id}`}>← Máquina {id}</Link>
      </p>
      <h1>Backups — {id}</h1>
      {mensaje && <p>{mensaje}</p>}
      {backups.length === 0 ? (
        <p>Todavía no hay backups (se crean automáticamente antes de cada guardado).</p>
      ) : (
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
                <td>{(b.tamano_bytes / 1024).toFixed(1)} KB</td>
                <td>
                  <button onClick={() => onRestaurar(b.nombre)}>Restaurar este backup</button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}
