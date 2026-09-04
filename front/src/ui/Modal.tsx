import { useEffect, useRef, type ReactNode } from "react";
import { createPortal } from "react-dom";

/**
 * Diálogo modal con la misma anatomía que los Toplevel del escritorio:
 * franja de color con el título arriba, cuerpo con scroll propio, y footer
 * con los botones. `Esc` cierra, igual que allá.
 *
 * `ancho` se expresa en píxeles para poder copiar los tamaños exactos de
 * cada diálogo del escritorio (780x580 para duplicados, 720x600 para
 * importar, etc.).
 */
export default function Modal({
  titulo,
  ancho = 640,
  peligro = false,
  ayuda,
  footer,
  onCerrar,
  children,
}: {
  titulo: string;
  ancho?: number;
  peligro?: boolean;
  ayuda?: ReactNode;
  footer?: ReactNode;
  onCerrar: () => void;
  children?: ReactNode;
}) {
  const cajaRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const previo = document.activeElement as HTMLElement | null;
    const overflowPrevio = document.body.style.overflow;
    document.body.style.overflow = "hidden";

    // Enfocar el primer control del diálogo, como hace `focus_set()` en el
    // escritorio: el operario puede empezar a tipear sin tocar el mouse.
    const foco = cajaRef.current?.querySelector<HTMLElement>(
      "input:not([type=hidden]), select, textarea, button",
    );
    foco?.focus();

    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        e.stopPropagation();
        onCerrar();
      }
    };
    document.addEventListener("keydown", onKey, true);
    return () => {
      document.removeEventListener("keydown", onKey, true);
      document.body.style.overflow = overflowPrevio;
      previo?.focus?.();
    };
  }, [onCerrar]);

  return createPortal(
    <div
      className="ui-modal-fondo"
      onMouseDown={(e) => {
        if (e.target === e.currentTarget) onCerrar();
      }}
    >
      <div
        ref={cajaRef}
        className={`ui-modal${peligro ? " ui-modal--peligro" : ""}`}
        style={{ maxWidth: ancho }}
        role="dialog"
        aria-modal="true"
        aria-label={titulo}
      >
        <div className="ui-modal__header">
          <h2 className="ui-modal__titulo">{titulo}</h2>
          <button
            type="button"
            className="ui-modal__cerrar"
            aria-label="Cerrar"
            onClick={onCerrar}
          >
            ×
          </button>
        </div>
        <div className="ui-modal__cuerpo">
          {ayuda && <p className="ui-modal__ayuda">{ayuda}</p>}
          {children}
        </div>
        {footer && <div className="ui-modal__footer">{footer}</div>}
      </div>
    </div>,
    document.body,
  );
}

/** Empuja los botones que siguen hacia la derecha del footer. */
export function EspacioFooter() {
  return <span className="ui-modal__footer-sep" />;
}
