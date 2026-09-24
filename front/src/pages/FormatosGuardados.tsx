import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api, type FormatoDetalle, type FormatoResumen, type PantallaAsistente } from "../api";
import Header from "../components/Header";
import { useDialogos, useToast } from "../ui";

const PANTALLA_LABEL: Record<PantallaAsistente, string> = {
  mediciones: "Mediciones",
  plantilla: "Generador desde plantilla",
  recetas_por_area: "Recetas por área",
};

function formatearFecha(iso: string | null): string {
  if (!iso) return "—";
  try {
    return new Date(iso).toLocaleString();
  } catch {
    return iso;
  }
}

export default function FormatosGuardados() {
  const [formatos, setFormatos] = useState<FormatoResumen[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [detalle, setDetalle] = useState<FormatoDetalle | null>(null);
  const [cargandoDetalle, setCargandoDetalle] = useState<string | null>(null);
  const [renombrando, setRenombrando] = useState<string | null>(null);
  const [nombreTipeado, setNombreTipeado] = useState("");
  const { confirmar, avisar } = useDialogos();
  const toast = useToast();

  const cargar = async () => {
    setError(null);
    try {
      const r = await api.listarFormatos();
      setFormatos(r);
    } catch (e) {
      setError(String(e));
    }
  };

  useEffect(() => {
    void cargar();
  }, []);

  const onVerDetalle = async (f: FormatoResumen) => {
    setCargandoDetalle(f.id);
    try {
      const d = await api.obtenerFormato(f.id);
      setDetalle(d);
    } catch (e) {
      await avisar({ titulo: "No se pudo abrir el formato", mensaje: String(e), tipo: "error" });
    } finally {
      setCargandoDetalle(null);
    }
  };

  const onEmpezarRenombre = (f: FormatoResumen) => {
    setRenombrando(f.id);
    setNombreTipeado(f.nombre);
  };

  const onConfirmarRenombre = async (id: string) => {
    const nombre = nombreTipeado.trim();
    if (!nombre) return;
    try {
      const actualizado = await api.renombrarFormato(id, nombre);
      setFormatos((prev) => prev?.map((f) => (f.id === id ? actualizado : f)) ?? null);
      if (detalle?.id === id) setDetalle({ ...detalle, nombre: actualizado.nombre });
      toast.mostrar("Formato renombrado.", "aviso");
    } catch (e) {
      await avisar({ titulo: "No se pudo renombrar", mensaje: String(e), tipo: "error" });
    } finally {
      setRenombrando(null);
    }
  };

  const onBorrar = async (f: FormatoResumen) => {
    const ok = await confirmar({
      titulo: "Borrar formato",
      mensaje: `¿Borrar el formato "${f.nombre}"? La próxima vez que suban un archivo así, el chat va a volver a preguntar cómo procesarlo.`,
      peligro: true,
      textoOk: "Borrar",
      textoCancelar: "Cancelar",
    });
    if (!ok) return;
    try {
      await api.borrarFormato(f.id);
      setFormatos((prev) => prev?.filter((x) => x.id !== f.id) ?? null);
      if (detalle?.id === f.id) setDetalle(null);
      toast.mostrar("Formato borrado.", "aviso");
    } catch (e) {
      await avisar({ titulo: "No se pudo borrar", mensaje: String(e), tipo: "error" });
    }
  };

  return (
    <div className="pagina">
      <Header />
      <p className="breadcrumbs">
        <Link to="/herramientas">Herramientas</Link>
        <span className="sep">/</span>
        <strong>Formatos guardados</strong>
      </p>
      <h1>Formatos guardados</h1>
      <p className="muted">
        Reglas que el chat aprendió de las explicaciones confirmadas en Mediciones, Generador desde
        plantilla y Recetas por área. Son compartidas por todos los usuarios.
      </p>

      {error && <p className="error">{error}</p>}

      {formatos && formatos.length === 0 && (
        <p className="muted">Todavía no se guardó ningún formato.</p>
      )}

      {formatos && formatos.length > 0 && (
        <div className="table-wrap">
        <table>
          <thead>
            <tr>
              <th>Nombre</th>
              <th>Pantalla</th>
              <th>Usos</th>
              <th>Creado por</th>
              <th>Creado</th>
              <th>Último uso</th>
              <th></th>
            </tr>
          </thead>
          <tbody>
            {formatos.map((f) => (
              <tr key={f.id}>
                <td>
                  {renombrando === f.id ? (
                    <input
                      autoFocus
                      value={nombreTipeado}
                      onChange={(e) => setNombreTipeado(e.target.value)}
                      onKeyDown={(e) => {
                        if (e.key === "Enter") void onConfirmarRenombre(f.id);
                        if (e.key === "Escape") setRenombrando(null);
                      }}
                      onBlur={() => void onConfirmarRenombre(f.id)}
                    />
                  ) : (
                    <button
                      className="btn-secondary"
                      onClick={() => void onVerDetalle(f)}
                      disabled={cargandoDetalle === f.id}
                    >
                      {f.nombre}
                    </button>
                  )}
                </td>
                <td>{PANTALLA_LABEL[f.pantalla] ?? f.pantalla}</td>
                <td>{f.usos}</td>
                <td>{f.creado_por}</td>
                <td>{formatearFecha(f.creado)}</td>
                <td>{formatearFecha(f.ultimo_uso)}</td>
                <td>
                  <div className="toolbar">
                    <button className="btn-secondary" onClick={() => onEmpezarRenombre(f)}>
                      Renombrar
                    </button>
                    <button className="btn-secondary" onClick={() => void onBorrar(f)}>
                      Borrar
                    </button>
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        </div>
      )}

      {detalle && (
        <div className="card" style={{ marginTop: "1.5rem" }}>
          <h2 style={{ marginTop: 0 }}>{detalle.nombre}</h2>
          <p className="muted">Explicación original del usuario:</p>
          <p style={{ whiteSpace: "pre-wrap" }}>{detalle.explicacion || "(sin explicación)"}</p>
          <p className="muted">Regla anclada:</p>
          <pre style={{ overflowX: "auto", background: "var(--surface-alt)", padding: "0.75rem", borderRadius: "var(--radio-lg)" }}>
            {JSON.stringify(detalle.regla, null, 2)}
          </pre>
          <button className="btn-secondary" onClick={() => setDetalle(null)}>
            Cerrar
          </button>
        </div>
      )}
    </div>
  );
}
