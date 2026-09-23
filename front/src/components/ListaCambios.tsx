import type { CambioEditorRecetas } from "../api";

/** Tabla de cambios detectados (parámetro, producto, valor anterior/nuevo).
 *  Componente genérico: si en el futuro otra pantalla necesita mostrar un
 *  diff parecido, se reusa tal cual. */
export default function ListaCambios({ cambios }: { cambios: CambioEditorRecetas[] }) {
  if (cambios.length === 0) {
    return <p className="muted">No se detectaron cambios.</p>;
  }
  return (
    <div className="table-wrap">
      <table>
        <thead>
          <tr>
            <th>Parámetro</th>
            <th>Producto</th>
            <th>Valor anterior</th>
            <th>Valor nuevo</th>
          </tr>
        </thead>
        <tbody>
          {cambios.map((c, i) => (
            <tr key={i}>
              <td>{c.parametro}</td>
              <td>{c.producto}</td>
              <td className="mono">{c.valor_anterior || <span className="muted">(vacío)</span>}</td>
              <td className="mono">{c.valor_nuevo || <span className="muted">(vacío)</span>}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
