import { useRef, useState } from "react";
import { Link } from "react-router-dom";
import { api, type HallazgoValidacion, type ReporteRecetasPorArea } from "../api";
import AsistentePanel from "../components/AsistentePanel";
import Header from "../components/Header";

function ListaHallazgos({ titulo, hallazgos }: { titulo: string; hallazgos: HallazgoValidacion[] }) {
  if (hallazgos.length === 0) return null;
  return (
    <div className="error" style={{ marginTop: "0.75rem" }}>
      <strong>{titulo}</strong>
      <ul style={{ margin: "0.35rem 0 0" }}>
        {hallazgos.map((h, i) => (
          <li key={i}>
            {h.archivo}: {h.mensaje}
          </li>
        ))}
      </ul>
    </div>
  );
}

function descargarBlob(blob: Blob, nombreArchivo: string) {
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = nombreArchivo;
  a.click();
  URL.revokeObjectURL(url);
}

function nombreZip(listado: File): string {
  const base = listado.name.includes(".")
    ? listado.name.slice(0, listado.name.lastIndexOf("."))
    : listado.name;
  return `${base}_recetas.zip`;
}

export default function RecetasPorArea() {
  const [listado, setListado] = useState<File | null>(null);
  const [previsualizando, setPrevisualizando] = useState(false);
  const [generando, setGenerando] = useState(false);
  const [reporte, setReporte] = useState<ReporteRecetasPorArea | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [auditando, setAuditando] = useState(false);
  const [hallazgosAuditoria, setHallazgosAuditoria] = useState<HallazgoValidacion[] | null>(null);
  const listadoInput = useRef<HTMLInputElement>(null);

  const onPrevisualizar = async () => {
    if (!listado) return;
    setPrevisualizando(true);
    setError(null);
    setReporte(null);
    try {
      const r = await api.previsualizarRecetasPorArea(listado);
      setReporte(r);
    } catch (e) {
      setError(String(e));
    } finally {
      setPrevisualizando(false);
    }
  };

  const onGenerar = async () => {
    if (!listado) return;
    setGenerando(true);
    setError(null);
    try {
      const blob = await api.generarRecetasPorArea(listado);
      descargarBlob(blob, nombreZip(listado));
    } catch (e) {
      setError(String(e));
    } finally {
      setGenerando(false);
    }
  };

  const onAuditar = async () => {
    setAuditando(true);
    setError(null);
    try {
      const r = await api.auditarRecetasPorArea();
      setHallazgosAuditoria(r.hallazgos);
    } catch (e) {
      setError(String(e));
    } finally {
      setAuditando(false);
    }
  };

  const onNuevoArchivo = () => {
    setListado(null);
    setReporte(null);
    setError(null);
    if (listadoInput.current) listadoInput.current.value = "";
  };

  return (
    <div className="pagina">
      <AsistentePanel pantallaActual="/recetas-por-area" listadoRecetas={listado} />
      <Header />
      <p className="breadcrumbs">
        <Link to="/herramientas">Herramientas</Link>
        <span className="sep">/</span>
        <strong>Recetas por área</strong>
      </p>
      <h1>Generar recetas por área</h1>
      <p className="muted">
        Subí el listado (columnas <code>sellado</code>, <code>amortiguador</code> y{" "}
        <code>área</code>). Por cada registro se generan todas las recetas de su área (HD, GPS1 o
        GPS2), una por cada variante de operación del catálogo de referencia — solo cambian el
        código de sellado y el amortiguador, el resto queda igual que la plantilla de esa área.
      </p>

      <div className="card" style={{ marginTop: "1rem", marginBottom: "1.5rem" }}>
        <h2>1. Elegí el listado</h2>
        <input
          ref={listadoInput}
          type="file"
          style={{ maxWidth: "320px" }}
          onChange={(e) => {
            setListado(e.target.files?.[0] ?? null);
            setReporte(null);
          }}
        />

        <h2 style={{ marginTop: "1.5rem" }}>2. Previsualizar</h2>
        <button onClick={() => void onPrevisualizar()} disabled={!listado || previsualizando}>
          {previsualizando ? "Analizando…" : "Previsualizar"}
        </button>
      </div>

      <div className="card" style={{ marginBottom: "1.5rem" }}>
        <h2>Auditar recetas existentes</h2>
        <p className="muted">
          Revisa las plantillas de referencia de docs/Recetas/ (sin subir nada) buscando
          inconsistencias: código que no coincide con el nombre del archivo, TEP que no coincide
          con el sufijo de operación, o variantes del mismo sellado con datos distintos entre sí.
        </p>
        <button onClick={() => void onAuditar()} disabled={auditando}>
          {auditando ? "Auditando…" : "Auditar recetas existentes"}
        </button>
        {hallazgosAuditoria && hallazgosAuditoria.length === 0 && (
          <p className="badge badge-ok" style={{ marginTop: "0.75rem" }}>
            No se encontraron inconsistencias.
          </p>
        )}
        {hallazgosAuditoria && hallazgosAuditoria.length > 0 && (
          <ListaHallazgos
            titulo={`Se encontraron ${hallazgosAuditoria.length} inconsistencia(s):`}
            hallazgos={hallazgosAuditoria}
          />
        )}
      </div>

      {error && <p className="error">{error}</p>}

      {reporte && (
        <div className="card">
          <h2>Se van a generar {reporte.cantidad_archivos} archivo(s)</h2>

          <p className="muted">
            Por área:{" "}
            {Object.entries(reporte.areas_usadas)
              .map(([area, n]) => `${area}: ${n} registro(s)`)
              .join(" · ") || "ninguna"}
          </p>

          {reporte.filas_sin_area.length > 0 && (
            <p className="error">
              Filas cuya área no coincide con ningún catálogo conocido (no generan nada):{" "}
              {reporte.filas_sin_area.join(", ")}.
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

          <ListaHallazgos titulo="Problemas en el listado:" hallazgos={reporte.hallazgos_listado} />
          <ListaHallazgos
            titulo="Las plantillas de referencia de estas áreas tienen inconsistencias conocidas:"
            hallazgos={reporte.hallazgos_catalogo}
          />

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
