/**
 * Barra de estado inferior: a la izquierda el último mensaje de la app
 * ("Cambios guardados", "⚠ Cambios SIN guardar…"), a la derecha el contador
 * de registros y la versión, que abre "Acerca de". Copia la franja de
 * `_build_ui` (máquina232/src/app.py:3547).
 */
export type TonoEstado = "normal" | "aviso" | "error";

export default function BarraEstado({
  mensaje,
  tono = "normal",
  cuenta,
  version,
  onAcercaDe,
}: {
  mensaje: string;
  tono?: TonoEstado;
  cuenta: string;
  version?: string;
  onAcercaDe?: () => void;
}) {
  const claseTono =
    tono === "aviso" ? " mq__estado--aviso" : tono === "error" ? " mq__estado--error" : "";
  return (
    <div className="mq__estado">
      <span className={claseTono.trim()}>{mensaje}</span>
      <span className="mq__estado-cuenta">{cuenta}</span>
      {version && (
        <button type="button" className="mq__estado-version" onClick={onAcercaDe}>
          v{version}
        </button>
      )}
    </div>
  );
}
