import { useEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";
import { api, type ResultadoMediciones } from "../api";
import Header from "../components/Header";

export default function Mediciones() {
  const [iaDisponible, setIaDisponible] = useState<boolean | null>(null);
  const [iaMensaje, setIaMensaje] = useState<string>("");
  const [archivo, setArchivo] = useState<File | null>(null);
  const [anotaciones, setAnotaciones] = useState<File | null>(null);
  const [useAi, setUseAi] = useState(true);
  const [procesando, setProcesando] = useState(false);
  const [resultado, setResultado] = useState<ResultadoMediciones | null>(null);
  const [error, setError] = useState<string | null>(null);
  const archivoInput = useRef<HTMLInputElement>(null);
  const anotacionesInput = useRef<HTMLInputElement>(null);

  useEffect(() => {
    api
      .estadoIA()
      .then((s) => {
        setIaDisponible(s.disponible);
        setIaMensaje(s.mensaje);
        setUseAi(s.disponible);
      })
      .catch((e) => setIaMensaje(String(e)));
  }, []);

  const onProcesar = async () => {
    if (!archivo) return;
    setProcesando(true);
    setError(null);
    setResultado(null);
    try {
      const r = await api.procesarMediciones(archivo, anotaciones, useAi);
      setResultado(r);
    } catch (e) {
      setError(String(e));
    } finally {
      setProcesando(false);
    }
  };

  const onNuevoArchivo = () => {
    setArchivo(null);
    setAnotaciones(null);
    setResultado(null);
    setError(null);
    if (archivoInput.current) archivoInput.current.value = "";
    if (anotacionesInput.current) anotacionesInput.current.value = "";
  };

  return (
    <div className="pagina">
      <Header />
      <p className="breadcrumbs">
        <Link to="/">Máquinas</Link>
        <span className="sep">/</span>
        <strong>Mediciones</strong>
      </p>
      <h1>Tabular mediciones</h1>
      <p className="muted">
        Subí el archivo de datos de un ensayo (y, si tenés, el archivo con anotaciones) para
        generar un Excel con los nombres de cada columna prolijados.
      </p>

      {iaDisponible === false && (
        <p className="error">La IA local no está disponible: {iaMensaje}. Igual podés procesar el archivo sin IA (se usan los nombres originales del equipo).</p>
      )}
      {iaDisponible === true && <p className="badge badge-ok">{iaMensaje}</p>}

      <div className="card" style={{ marginTop: "1rem", marginBottom: "1.5rem" }}>
        <h2>1. Elegí los archivos</h2>
        <div className="toolbar" style={{ alignItems: "flex-start" }}>
          <div style={{ minWidth: "280px" }}>
            <label className="muted">Archivo de datos (obligatorio)</label>
            <input
              ref={archivoInput}
              type="file"
              onChange={(e) => setArchivo(e.target.files?.[0] ?? null)}
            />
          </div>
          <div style={{ minWidth: "280px" }}>
            <label className="muted">Archivo con anotaciones (opcional)</label>
            <input
              ref={anotacionesInput}
              type="file"
              onChange={(e) => setAnotaciones(e.target.files?.[0] ?? null)}
            />
          </div>
        </div>

        <h2 style={{ marginTop: "1.5rem" }}>2. IA local</h2>
        <label style={{ display: "flex", alignItems: "center", gap: "0.6rem", fontWeight: 500 }}>
          <input
            type="checkbox"
            style={{ width: "1.3rem", height: "1.3rem" }}
            checked={useAi}
            disabled={iaDisponible === false}
            onChange={(e) => setUseAi(e.target.checked)}
          />
          Usar la IA local para prolijar los nombres de los campos
        </label>
        <p className="muted">
          Sin IA, el Excel sale igual pero con los nombres crudos que trae el equipo.
        </p>

        <h2 style={{ marginTop: "1.5rem" }}>3. Procesar</h2>
        <button onClick={onProcesar} disabled={!archivo || procesando}>
          {procesando ? "Procesando…" : "Generar Excel"}
        </button>
        {procesando && (
          <p className="muted">
            {useAi
              ? "Puede tardar unos segundos: la IA local está trabajando."
              : "Procesando el archivo…"}
          </p>
        )}
      </div>

      {error && <p className="error">{error}</p>}

      {resultado && (
        <div className="card">
          <h2>Listo: {resultado.out_filename}</h2>
          <table>
            <tbody>
              <tr>
                <td>Registros encontrados</td>
                <td>
                  <strong>{resultado.records}</strong>
                </td>
              </tr>
              <tr>
                <td>Campos por registro</td>
                <td>{resultado.fields}</td>
              </tr>
              <tr>
                <td>Configuraciones detectadas</td>
                <td>{resultado.configs}</td>
              </tr>
              <tr>
                <td>Líneas sin reconocer</td>
                <td>{resultado.unparsed}</td>
              </tr>
            </tbody>
          </table>
          {resultado.ai_messages.length > 0 && (
            <ul className="muted">
              {resultado.ai_messages.map((m, i) => (
                <li key={i}>{m}</li>
              ))}
            </ul>
          )}
          <div className="toolbar" style={{ marginTop: "1rem" }}>
            <a className="btn" href={resultado.download_url}>
              Descargar Excel
            </a>
            <button className="btn-secondary" onClick={onNuevoArchivo}>
              Procesar otro archivo
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
