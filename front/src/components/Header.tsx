import { Link } from "react-router-dom";

export default function Header() {
  return (
    <header className="app-header">
      <Link to="/" className="brand">
        <span className="brand-mark">Configurador de Planta</span>
        <span className="brand-sub">Recetas y parámetros de máquina</span>
      </Link>
      <nav>
        <Link to="/mediciones" className="btn btn-secondary">
          Tabular mediciones
        </Link>
      </nav>
    </header>
  );
}
