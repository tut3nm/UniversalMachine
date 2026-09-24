import { useRef, useState } from "react";
import { Link } from "react-router-dom";
import { api, type ReportePlantillasMasivas } from "../api";
import AsistentePanel from "../components/AsistentePanel";
import Header from "../components/Header";

/** Descarga un Blob como si fuera un <a download>, sin necesidad de que el
 *  backend guarde una copia del archivo en el servidor. */
function descargarBlob(blob: Blob, nombreArchivo: string) {
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = nombreArchivo;
  a.click();
  URL.revokeObjectURL(url);
}

/** Nombre de archivo sugerido para el .zip, a partir del de la plantilla. */
function nombreZip(plantilla: File): string {
  const base = plantilla.name.includes(".")
    ? plantilla.name.slice(0, plantilla.name.lastIndexOf("."))
    : plantilla.name;
  return `${base}.zip`;
}

export default function GenerarRecetas() {
  const [plantilla, setPlantilla] = useState<File | null>(null);
  const [listado, setListado] = useState<File | null>(null);
  const [previsualizando, setPrevisualizando] = useState(false);
  const [generando, setGenerando] = useState(false);
  const [reporte, setReporte] = useState<ReportePlantillasMasivas | null>(null);
  const [error, setError] = useState<string | null>(null);
  const plantillaInput = useRef<HTMLInputElement>(null);
  const listadoInput = useRef<HTMLInputElement>(null);

  const onPrevisualizar = async () => {
    if (!plantilla || !listado) return;
    setPrevisualizando(true);
    setError(null);
    setReporte(null);
    try {
      const r = await api.previsualizarPlantillasMasivas(plantilla, listado);
      setReporte(r);
    } catch (e) {
      setError(String(e));
    } finally {
      setPrevisualizando(false);
    }
  };

  const onGenerar = async () => {
    if (!plantilla || !listado) return;
    setGenerando(true);
    setError(null);
    try {
      const blob = await api.generarPlantillasMasivas(plantilla, listado);
      descargarBlob(blob, nombreZip(plantilla));
    } catch (e) {
      setError(String(e));
    } finally {
      setGenerando(false);
    }
  };

  const onNuevoArchivo = () => {
    setPlantilla(null);
    setListado(null);
    setReporte(null);
    setError(null);
    if (plantillaInput.current) plantillaInput.current.value = "";
    if (listadoInput.current) listadoInput.current.value = "";
  };

  return (
    <div className="pagina">
      <AsistentePanel pantalla="plantilla" archivos={{ plantilla, listado }} />
      <Header />
      <p className="breadcrumbs">
        <Link to="/">Máquinas</Link>
        <span className="sep">/</span>
        <strong>Generador de recetas</strong>
      </p>
      <h1>Generar archivos desde plantilla + listado</h1>
      <p className="muted">
        Subí una plantilla (un archivo de ejemplo ya completo, con los valores que varían
        marcados entre llaves) y un listado con un registro por fila. Se genera un archivo por
        registro, con el mismo formato que la plantilla.
      </p>

      <div className="card" style={{ marginTop: "1rem", marginBottom: "1.5rem" }}>
        <h2>1. Elegí los archivos</h2>
        <div className="toolbar" style={{ alignItems: "flex-start" }}>
          <div style={{ minWidth: "280px" }}>
            <label className="muted">Plantilla (.txt/.csv, con campos entre {"{...}"})</label>
            <input
              ref={plantillaInput}
              type="file"
              onChange={(e) => {
                setPlantilla(e.target.files?.[0] ?? null);
                setReporte(null);
              }}
            />
          </div>
          <div style={{ minWidth: "280px" }}>
            <label className="muted">Listado (.txt/.csv, con fila de encabezado)</label>
            <input
              ref={listadoInput}
              type="file"
              onChange={(e) => {
                setListado(e.target.files?.[0] ?? null);
                setReporte(null);
              }}
            />
          </div>
        </div>

        <h2 style={{ marginTop: "1.5rem" }}>2. Previsualizar</h2>
        <button onClick={() => void onPrevisualizar()} disabled={!plantilla || !listado || previsualizando}>
          {previsualizando ? "Analizando…" : "Previsualizar"}
        </button>
      </div>

      {error && <p className="error">{error}</p>}

      {reporte && (
        <div className="card">
          <h2>Se van a generar {reporte.cantidad_archivos} archivo(s)</h2>

          {reporte.columnas_sin_uso.length > 0 && (
            <p className="muted">
              Columnas del listado que ningún campo de la plantilla usa:{" "}
              {reporte.columnas_sin_uso.join(", ")}.
            </p>
          )}
          {reporte.lineas_ignoradas.length > 0 && (
            <p className="muted">
              Líneas de la plantilla sin columna reconocible en su comentario (quedan iguales en
              todos los archivos generados): {reporte.lineas_ignoradas.map((i) => i + 1).join(", ")}.
            </p>
          )}

          <p className="muted">Primeros nombres de archivo:</p>
          <ul className="muted">
            {reporte.nombres_archivo.slice(0, 10).map((n) => (
              <li key={n}>{n}</li>
            ))}
            {reporte.nombres_archivo.length > 10 && (
              <li>… y {reporte.nombres_archivo.length - 10} más.</li>
            )}
          </ul>

          <div className="toolbar" style={{ marginTop: "1rem" }}>
            <button className="btn" onClick={() => void onGenerar()} disabled={generando}>
              {generando ? "Generando…" : "Generar y descargar .zip"}
            </button>
            <button className="btn-secondary" onClick={onNuevoArchivo}>
              Empezar de nuevo
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
