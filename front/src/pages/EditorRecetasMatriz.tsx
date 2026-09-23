import { useRef, useState } from "react";
import { Link } from "react-router-dom";
import { api, type ReporteAplicarEditorRecetas } from "../api";
import Header from "../components/Header";
import ListaCambios from "../components/ListaCambios";

function descargarBlob(blob: Blob, nombreArchivo: string) {
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = nombreArchivo;
  a.click();
  URL.revokeObjectURL(url);
}

export default function EditorRecetasMatriz() {
  // -- paso 1: exportar --------------------------------------------------
  const [csv, setCsv] = useState<File | null>(null);
  const [exportando, setExportando] = useState(false);
  const [exportado, setExportado] = useState(false);
  const [errorExportar, setErrorExportar] = useState<string | null>(null);
  const csvInput = useRef<HTMLInputElement>(null);

  // -- paso 2: aplicar -----------------------------------------------------
  const [csvOriginal, setCsvOriginal] = useState<File | null>(null);
  const [xlsxEditado, setXlsxEditado] = useState<File | null>(null);
  const [previsualizando, setPrevisualizando] = useState(false);
  const [reporte, setReporte] = useState<ReporteAplicarEditorRecetas | null>(null);
  const [descargando, setDescargando] = useState(false);
  const [errorAplicar, setErrorAplicar] = useState<string | null>(null);
  const csvOriginalInput = useRef<HTMLInputElement>(null);
  const xlsxEditadoInput = useRef<HTMLInputElement>(null);

  const onExportar = async () => {
    if (!csv) return;
    setExportando(true);
    setErrorExportar(null);
    try {
      const { blob, nombreArchivo } = await api.editorRecetasExportar(csv);
      descargarBlob(blob, nombreArchivo);
      setExportado(true);
    } catch (e) {
      setErrorExportar(String(e));
    } finally {
      setExportando(false);
    }
  };

  const onPrevisualizar = async () => {
    if (!csvOriginal || !xlsxEditado) return;
    setPrevisualizando(true);
    setErrorAplicar(null);
    setReporte(null);
    try {
      const r = await api.editorRecetasAplicar(csvOriginal, xlsxEditado);
      setReporte(r);
    } catch (e) {
      setErrorAplicar(String(e));
    } finally {
      setPrevisualizando(false);
    }
  };

  const onDescargar = async () => {
    if (!csvOriginal || !xlsxEditado) return;
    setDescargando(true);
    setErrorAplicar(null);
    try {
      const { blob, nombreArchivo } = await api.editorRecetasAplicarYDescargar(csvOriginal, xlsxEditado);
      descargarBlob(blob, nombreArchivo);
    } catch (e) {
      setErrorAplicar(String(e));
    } finally {
      setDescargando(false);
    }
  };

  return (
    <div className="pagina">
      <Header />
      <p className="breadcrumbs">
        <Link to="/herramientas">Herramientas</Link>
        <span className="sep">/</span>
        <strong>Editor de recetas (matriz)</strong>
      </p>
      <h1>Editar recetas tipo matriz</h1>
      <p className="muted">
        Para archivos <code>.csv</code> de receta con un parámetro por fila y un producto por
        columna. El flujo tiene dos pasos: primero se exporta a un Excel cómodo para editar,
        después se sube ese Excel junto con el <code>.csv</code> original para reconstruirlo —
        solo cambian las celdas que efectivamente editaste, todo lo demás queda igual.
      </p>

      <div className="card" style={{ marginTop: "1rem", marginBottom: "1.5rem" }}>
        <h2>1. Exportar a Excel</h2>
        <input
          ref={csvInput}
          type="file"
          style={{ maxWidth: "320px" }}
          onChange={(e) => {
            setCsv(e.target.files?.[0] ?? null);
            setExportado(false);
          }}
        />
        <div className="toolbar" style={{ marginTop: "0.75rem" }}>
          <button onClick={() => void onExportar()} disabled={!csv || exportando}>
            {exportando ? "Generando…" : "Exportar a Excel"}
          </button>
        </div>
        {errorExportar && <p className="error">{errorExportar}</p>}
        {exportado && (
          <p className="badge badge-ok">
            Excel descargado. Editá los valores que necesites en la hoja "Recetas" y guardalo.
          </p>
        )}
      </div>

      <div className="card">
        <h2>2. Aplicar cambios al original</h2>
        <p className="muted">
          Subí el mismo <code>.csv</code> que usaste en el paso 1, y el Excel ya editado.
        </p>
        <div className="toolbar" style={{ alignItems: "flex-start" }}>
          <div style={{ minWidth: "280px" }}>
            <label className="muted">Archivo .csv original</label>
            <input
              ref={csvOriginalInput}
              type="file"
              onChange={(e) => {
                setCsvOriginal(e.target.files?.[0] ?? null);
                setReporte(null);
              }}
            />
          </div>
          <div style={{ minWidth: "280px" }}>
            <label className="muted">Excel ya editado (.xlsx)</label>
            <input
              ref={xlsxEditadoInput}
              type="file"
              onChange={(e) => {
                setXlsxEditado(e.target.files?.[0] ?? null);
                setReporte(null);
              }}
            />
          </div>
        </div>

        <div className="toolbar" style={{ marginTop: "0.75rem" }}>
          <button
            onClick={() => void onPrevisualizar()}
            disabled={!csvOriginal || !xlsxEditado || previsualizando}
          >
            {previsualizando ? "Comparando…" : "Ver cambios"}
          </button>
        </div>

        {errorAplicar && <p className="error">{errorAplicar}</p>}

        {reporte && (
          <div style={{ marginTop: "1rem" }}>
            <h3>{reporte.cantidad_cambios} cambio(s) detectado(s)</h3>
            <ListaCambios cambios={reporte.cambios} />

            {reporte.advertencias.length > 0 && (
              <ul className={reporte.bloqueado ? "error" : "muted"} style={{ marginTop: "0.75rem" }}>
                {reporte.advertencias.map((a, i) => (
                  <li key={i}>{a}</li>
                ))}
              </ul>
            )}

            {reporte.bloqueado ? (
              <p className="error" style={{ marginTop: "0.75rem" }}>
                No se puede descargar: la autoverificación del archivo reconstruido encontró un
                problema (ver ALERTA arriba). Revisá el Excel editado antes de reintentar.
              </p>
            ) : (
              <div className="toolbar" style={{ marginTop: "1rem" }}>
                <button className="btn" onClick={() => void onDescargar()} disabled={descargando}>
                  {descargando ? "Generando…" : "Descargar .csv actualizado"}
                </button>
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
