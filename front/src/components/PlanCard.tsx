import { useState } from "react";
import { Link } from "react-router-dom";
import { api, type ProgramaAsistente, type RespuestaInterpretar } from "../api";

/** Ruta de la pantalla que resuelve cada operacion gruesa que no sea
 *  'generar_recetas_por_area' (esa se ejecuta desde esta misma tarjeta). */
const RUTA_POR_OPERACION: Record<string, string> = {
  generar_desde_plantilla: "/generador-recetas",
  tabular_mediciones: "/mediciones",
};

function etiquetaOperacion(op: ProgramaAsistente): string {
  const args = Object.entries(op.args)
    .map(([k, v]) => `${k}: ${Array.isArray(v) ? v.join(", ") : String(v)}`)
    .join(" · ");
  return args ? `${op.op} (${args})` : op.op;
}

function descargarBlob(blob: Blob, nombreArchivo: string) {
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = nombreArchivo;
  a.click();
  URL.revokeObjectURL(url);
}

/**
 * La burbuja de respuesta del asistente. Todo el texto que muestra lo arma
 * este componente a partir de la ESTRUCTURA que devuelve /interpretar — el
 * modelo nunca redacta lo que el usuario lee (PLAN_ASISTENTE_IA.md, seccion
 * 1: "la IA no escribe prosa").
 */
export default function PlanCard({
  respuesta,
  texto,
  listado,
  pantallaActual,
}: {
  respuesta: RespuestaInterpretar;
  texto: string;
  listado: File | null;
  pantallaActual: string;
}) {
  const [ejecutando, setEjecutando] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [listo, setListo] = useState<{ nombreArchivo: string; cantidad: number } | null>(null);

  if (respuesta.desconocido) {
    return (
      <div className="plan-card plan-card--desconocido">
        <p>{respuesta.mensaje}</p>
      </div>
    );
  }

  if (respuesta.requiere_pantalla) {
    const ruta = RUTA_POR_OPERACION[respuesta.requiere_pantalla];
    const yaEstaAca = ruta === pantallaActual;
    return (
      <div className="plan-card">
        <p className="plan-card__descripcion">{respuesta.descripcion}</p>
        {yaEstaAca ? (
          <p className="muted">Esta es la pantalla correcta: subí los archivos arriba.</p>
        ) : (
          <p className="muted">
            Esa tarea se hace en otra pantalla: <Link to={ruta ?? "/herramientas"}>ir ahí</Link>.
          </p>
        )}
      </div>
    );
  }

  if (respuesta.requiere_listado) {
    return (
      <div className="plan-card">
        <p className="plan-card__descripcion">{respuesta.descripcion}</p>
        <p className="muted">Subí el listado arriba para poder armar el plan.</p>
      </div>
    );
  }

  if (respuesta.error_validacion) {
    return (
      <div className="plan-card">
        <p className="plan-card__descripcion">{respuesta.descripcion}</p>
        <p className="error">{respuesta.error_validacion}</p>
      </div>
    );
  }

  const onEjecutar = async () => {
    if (!listado) return;
    setEjecutando(true);
    setError(null);
    try {
      const { blob, nombreArchivo, resumen } = await api.ejecutarAsistente(
        respuesta.programa,
        listado,
        texto,
      );
      descargarBlob(blob, nombreArchivo);
      setListo({ nombreArchivo, cantidad: resumen.cantidad_archivos });
    } catch (e) {
      setError(String(e));
    } finally {
      setEjecutando(false);
    }
  };

  return (
    <div className="plan-card">
      <p className="plan-card__descripcion">{respuesta.descripcion}</p>

      <ul className="plan-card__operaciones">
        {respuesta.programa.map((op, i) => (
          <li key={i} className="plan-card__operacion">
            {etiquetaOperacion(op)}
          </li>
        ))}
      </ul>

      <p className="muted">Se van a generar {respuesta.cantidad_archivos ?? 0} archivo(s).</p>

      {respuesta.advertencias && respuesta.advertencias.length > 0 && (
        <ul className="plan-card__advertencias">
          {respuesta.advertencias.map((a, i) => (
            <li key={i}>{a}</li>
          ))}
        </ul>
      )}

      {respuesta.hallazgos && respuesta.hallazgos.length > 0 && (
        <ul className="plan-card__advertencias">
          {respuesta.hallazgos.map((h, i) => (
            <li key={i}>
              {h.archivo}: {h.mensaje}
            </li>
          ))}
        </ul>
      )}

      {error && <p className="error">{error}</p>}

      {listo ? (
        <p className="badge badge-ok">
          Listo: {listo.nombreArchivo} ({listo.cantidad} archivo(s))
        </p>
      ) : (
        <button className="ui-btn ui-btn--primary ui-btn--sm" onClick={() => void onEjecutar()} disabled={ejecutando || !listado}>
          {ejecutando ? "Generando…" : "Ejecutar y descargar"}
        </button>
      )}
    </div>
  );
}
