import { useEffect, useMemo, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { api, type Campo, type Registro } from "../api";
import Header from "../components/Header";

const PAGE_SIZE = 50;

export default function MaquinaDetalle() {
  const { id } = useParams<{ id: string }>();
  const [nombre, setNombre] = useState<string>("");
  const [campos, setCampos] = useState<Campo[] | null>(null);
  const [registros, setRegistros] = useState<Registro[] | null>(null);
  const [hash, setHash] = useState<string | null>(null);
  const [busqueda, setBusqueda] = useState("");
  const [pagina, setPagina] = useState(0);
  const [error, setError] = useState<string | null>(null);
  const [nuevo, setNuevo] = useState<Record<string, string>>({});
  const [mostrarAlta, setMostrarAlta] = useState(false);

  const cargar = () => {
    if (!id) return;
    api
      .obtenerMaquina(id)
      .then((m) => {
        setNombre(m.nombre);
        setCampos(m.campos);
      })
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

  const claveField = campos?.find((c) => c.rol === "clave")?.nombre_interno ?? "code";

  const filtrados = useMemo(() => {
    if (!registros) return [];
    return registros.filter(
      (r) =>
        !r.es_placeholder &&
        (busqueda === "" ||
          Object.values(r).some((v) => String(v).toLowerCase().includes(busqueda.toLowerCase()))),
    );
  }, [registros, busqueda]);

  const totalPaginas = Math.max(1, Math.ceil(filtrados.length / PAGE_SIZE));
  const pagInicio = pagina * PAGE_SIZE;
  const visibles = filtrados.slice(pagInicio, pagInicio + PAGE_SIZE);

  const onEditarCelda = async (index: number, campo: string, valorStr: string) => {
    if (!id) return;
    const c = campos?.find((c) => c.nombre_interno === campo);
    const valor = c?.tipo === "entero" || c?.tipo === "decimal" || c?.tipo === "entero_ceros" ? Number(valorStr) : valorStr;
    try {
      await api.actualizarRegistro(id, index, { [campo]: valor }, hash);
      cargar();
    } catch (e) {
      setError(String(e));
    }
  };

  const onEliminar = async (index: number, clave: string) => {
    if (!id) return;
    if (!confirm(`¿Eliminar el registro "${clave}"?`)) return;
    try {
      await api.eliminarRegistro(id, index, hash);
      cargar();
    } catch (e) {
      setError(String(e));
    }
  };

  const onCrear = async () => {
    if (!id) return;
    try {
      await api.crearRegistro(id, nuevo, hash);
      setNuevo({});
      setMostrarAlta(false);
      cargar();
    } catch (e) {
      setError(String(e));
    }
  };

  if (!id || !campos || !registros) {
    return (
      <div>
        <Header />
        {error ? <p className="error">Error: {error}</p> : <p>Cargando…</p>}
      </div>
    );
  }

  return (
    <div>
      <Header />
      <p className="breadcrumbs">
        <Link to="/">Máquinas</Link>
        <span className="sep">/</span>
        <strong>{nombre || id}</strong>
      </p>
      <h1>{nombre || `Máquina ${id}`}</h1>

      {error && <p className="error">{error}</p>}

      <div className="toolbar">
        <Link to={`/maquinas/${id}/backups`} className="btn btn-secondary">
          Backups
        </Link>
        <Link to={`/maquinas/${id}/historial`} className="btn btn-secondary">
          Historial
        </Link>
        <button onClick={() => setMostrarAlta((v) => !v)}>
          {mostrarAlta ? "Cancelar alta" : "+ Agregar registro"}
        </button>
      </div>

      <input
        className="search-bar"
        placeholder="Buscar por código o valor…"
        value={busqueda}
        onChange={(e) => {
          setBusqueda(e.target.value);
          setPagina(0);
        }}
      />

      {mostrarAlta && (
        <div className="card" style={{ marginBottom: "1.25rem" }}>
          <h2>Nuevo registro</h2>
          <div className="toolbar">
            {campos.map((c) => (
              <div key={c.nombre_interno} style={{ minWidth: "160px" }}>
                <label className="muted">{c.titulo_ui}</label>
                <input
                  placeholder={c.titulo_ui}
                  value={nuevo[c.nombre_interno] ?? ""}
                  onChange={(e) => setNuevo({ ...nuevo, [c.nombre_interno]: e.target.value })}
                />
              </div>
            ))}
          </div>
          <button onClick={onCrear} disabled={!nuevo[claveField]}>
            Guardar registro nuevo
          </button>
        </div>
      )}

      <div className="table-wrap">
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
            {visibles.map((r) => (
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
                  <button
                    className="btn-danger btn-small"
                    onClick={() => onEliminar(r.index, String(r[claveField] ?? ""))}
                  >
                    Eliminar
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <div className="toolbar" style={{ marginTop: "1rem" }}>
        <button
          className="btn-secondary btn-small"
          disabled={pagina === 0}
          onClick={() => setPagina((p) => Math.max(0, p - 1))}
        >
          ← Anterior
        </button>
        <span className="muted">
          Página {pagina + 1} de {totalPaginas} — {filtrados.length} de{" "}
          {registros.filter((r) => !r.es_placeholder).length} registros reales
        </span>
        <button
          className="btn-secondary btn-small"
          disabled={pagina >= totalPaginas - 1}
          onClick={() => setPagina((p) => Math.min(totalPaginas - 1, p + 1))}
        >
          Siguiente →
        </button>
      </div>
    </div>
  );
}
