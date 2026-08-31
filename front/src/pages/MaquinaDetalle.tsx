import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { api, type Campo, type Registro } from "../api";

export default function MaquinaDetalle() {
  const { id } = useParams<{ id: string }>();
  const [campos, setCampos] = useState<Campo[] | null>(null);
  const [registros, setRegistros] = useState<Registro[] | null>(null);
  const [hash, setHash] = useState<string | null>(null);
  const [busqueda, setBusqueda] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [nuevo, setNuevo] = useState<Record<string, string>>({});

  const cargar = () => {
    if (!id) return;
    api
      .obtenerMaquina(id)
      .then((m) => setCampos(m.campos))
      .catch((e) => setError(String(e)));
    api
      .listarRegistros(id)
      .then((r) => {
        setRegistros(r.registros);
        setHash(r.hash);
      })
      .catch((e) => setError(String(e)));
  };

  useEffect(cargar, [id]);

  if (error) return <p className="error">Error: {error}</p>;
  if (!id || !campos || !registros) return <p>Cargando…</p>;

  const claveField = campos.find((c) => c.rol === "clave")?.nombre_interno ?? "code";
  const filtrados = registros.filter(
    (r) =>
      !r.es_placeholder &&
      (busqueda === "" ||
        Object.values(r).some((v) => String(v).toLowerCase().includes(busqueda.toLowerCase()))),
  );

  const onEditarCelda = async (index: number, campo: string, valorStr: string) => {
    const c = campos.find((c) => c.nombre_interno === campo);
    const valor = c?.tipo === "entero" || c?.tipo === "decimal" ? Number(valorStr) : valorStr;
    try {
      await api.actualizarRegistro(id, index, { [campo]: valor }, hash);
      cargar();
    } catch (e) {
      setError(String(e));
    }
  };

  const onEliminar = async (index: number) => {
    if (!confirm("¿Eliminar este registro?")) return;
    try {
      await api.eliminarRegistro(id, index, hash);
      cargar();
    } catch (e) {
      setError(String(e));
    }
  };

  const onCrear = async () => {
    try {
      await api.crearRegistro(id, nuevo, hash);
      setNuevo({});
      cargar();
    } catch (e) {
      setError(String(e));
    }
  };

  return (
    <div>
      <p>
        <Link to="/">← Máquinas</Link>
        {" · "}
        <Link to={`/maquinas/${id}/backups`}>Backups</Link>
        {" · "}
        <Link to={`/maquinas/${id}/historial`}>Historial</Link>
      </p>
      <h1>Máquina {id}</h1>
      <input
        placeholder="Buscar…"
        value={busqueda}
        onChange={(e) => setBusqueda(e.target.value)}
      />
      <table>
        <thead>
          <tr>
            {campos.map((c) => (
              <th key={c.nombre_interno}>{c.titulo_ui}</th>
            ))}
            <th></th>
          </tr>
        </thead>
        <tbody>
          {filtrados.map((r) => (
            <tr key={r.index}>
              {campos.map((c) => (
                <td key={c.nombre_interno}>
                  {c.rol === "clave" ? (
                    String(r[c.nombre_interno] ?? "")
                  ) : (
                    <input
                      defaultValue={String(r[c.nombre_interno] ?? "")}
                      onBlur={(e) =>
                        e.target.value !== String(r[c.nombre_interno] ?? "") &&
                        onEditarCelda(r.index, c.nombre_interno, e.target.value)
                      }
                    />
                  )}
                </td>
              ))}
              <td>
                <button onClick={() => onEliminar(r.index)}>Eliminar</button>
              </td>
            </tr>
          ))}
          <tr>
            {campos.map((c) => (
              <td key={c.nombre_interno}>
                <input
                  placeholder={c.titulo_ui}
                  value={nuevo[c.nombre_interno] ?? ""}
                  onChange={(e) => setNuevo({ ...nuevo, [c.nombre_interno]: e.target.value })}
                />
              </td>
            ))}
            <td>
              <button onClick={onCrear} disabled={!nuevo[claveField]}>
                Agregar
              </button>
            </td>
          </tr>
        </tbody>
      </table>
      <p>
        {filtrados.length} de {registros.filter((r) => !r.es_placeholder).length} registros reales
      </p>
    </div>
  );
}
