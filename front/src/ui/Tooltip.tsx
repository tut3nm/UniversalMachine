import { useCallback, useRef, useState, type ReactNode } from "react";
import { createPortal } from "react-dom";

/**
 * Tooltip equivalente al de ttkbootstrap en el escritorio: aparece al pasar
 * el mouse o al enfocar con el teclado, y explica en una frase qué hace el
 * control. Se envuelve al hijo en un `span` propio en vez de clonarlo, para
 * que también funcione sobre botones deshabilitados — que en el navegador no
 * emiten eventos de mouse (ver `pointer-events: none` en ui.css).
 */
export default function Tooltip({
  texto,
  children,
}: {
  texto?: string;
  children: ReactNode;
}) {
  const anchorRef = useRef<HTMLSpanElement>(null);
  const [pos, setPos] = useState<{ x: number; y: number } | null>(null);

  const mostrar = useCallback(() => {
    const el = anchorRef.current;
    if (!el) return;
    const r = el.getBoundingClientRect();
    setPos({ x: r.left + r.width / 2, y: r.bottom + 8 });
  }, []);

  const ocultar = useCallback(() => setPos(null), []);

  /** Ya insertado en el DOM, corre el globo hacia adentro si se pasó de un
   *  borde de la ventana (los textos de ayuda son largos y muchos botones
   *  quedan pegados al borde izquierdo de la toolbar). */
  const ajustarAlBorde = useCallback((el: HTMLDivElement | null) => {
    if (!el) return;
    const r = el.getBoundingClientRect();
    const margen = 8;
    let dx = 0;
    if (r.left < margen) dx = margen - r.left;
    else if (r.right > window.innerWidth - margen) dx = window.innerWidth - margen - r.right;
    if (dx) el.style.transform = `translateX(calc(-50% + ${dx}px))`;
  }, []);

  if (!texto) return <>{children}</>;

  return (
    <>
      <span
        ref={anchorRef}
        className="ui-tooltip-anchor"
        onMouseEnter={mostrar}
        onMouseLeave={ocultar}
        onFocusCapture={mostrar}
        onBlurCapture={ocultar}
      >
        {children}
      </span>
      {pos &&
        createPortal(
          <div
            ref={ajustarAlBorde}
            role="tooltip"
            className="ui-tooltip"
            style={{ left: pos.x, top: pos.y, transform: "translateX(-50%)" }}
          >
            {texto}
          </div>,
          document.body,
        )}
    </>
  );
}
