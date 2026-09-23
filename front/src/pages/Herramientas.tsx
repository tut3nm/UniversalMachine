import { Link } from "react-router-dom";
import Header from "../components/Header";

interface Herramienta {
  to: string;
  titulo: string;
  descripcion: string;
}

const HERRAMIENTAS: Herramienta[] = [
  {
    to: "/recetas-por-area",
    titulo: "Generador de recetas por área",
    descripcion:
      "Subí el listado (sellado, amortiguador, área) y se generan automáticamente todas las recetas de esa área, a partir del catálogo de plantillas de referencia (HD/GPS1/GPS2).",
  },
  {
    to: "/generador-recetas",
    titulo: "Generador desde plantilla",
    descripcion:
      "Subí una plantilla de ejemplo (con los campos que varían marcados entre llaves) y un listado, y se genera un archivo por registro.",
  },
  {
    to: "/mediciones",
    titulo: "Tabular mediciones",
    descripcion:
      "Subí el archivo de datos de un ensayo y generá un Excel con los nombres de cada columna prolijados.",
  },
  {
    to: "/editor-recetas-matriz",
    titulo: "Editor de recetas (matriz)",
    descripcion:
      "Para archivos .csv de receta con un parámetro por fila y un producto por columna: exportá a Excel, editá, y volvé a aplicar los cambios al original.",
  },
];

export default function Herramientas() {
  return (
    <div className="pagina">
      <Header />
      <h1>Herramientas</h1>
      <p className="muted">Elegí la tarea que necesitás hacer.</p>

      <div
        style={{
          display: "grid",
          gridTemplateColumns: "repeat(auto-fill, minmax(260px, 1fr))",
          gap: "1rem",
          marginTop: "1.25rem",
        }}
      >
        {HERRAMIENTAS.map((h) => (
          <Link
            key={h.to}
            to={h.to}
            className="card"
            style={{ display: "block", textDecoration: "none", color: "inherit" }}
          >
            <h2 style={{ marginTop: 0 }}>{h.titulo}</h2>
            <p className="muted" style={{ marginBottom: 0 }}>
              {h.descripcion}
            </p>
          </Link>
        ))}
      </div>
    </div>
  );
}
