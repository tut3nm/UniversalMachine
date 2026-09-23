import { useCallback, useRef, useState } from "react";
import { createPortal } from "react-dom";

/**
 * Tarjeta de prompt precargado del asistente: al pasar el mouse (o enfocar
 * con teclado) muestra una explicacion breve de para que sirve; al hacer
 * click/tap, dispara `onSeleccionar` de inmediato — en touch no hay "hover"
 * real, asi que el tap tiene que ser la accion primaria, no un segundo paso
 * despues de un "reveal" (PLAN_ASISTENTE_IA.md seccion 6: "responde a hover,
 * focus y tap"). Mismo patron de portal que ui/Tooltip.tsx, pero con mas
 * contenido (titulo + ayuda) y position:fixed centrado sobre la tarjeta.
 */
export default function HoverCard({
  titulo,
  ayuda,
  onSeleccionar,
}: {
  titulo: string;
  ayuda: string;
  onSeleccionar: () => void;
}) {
  const anchorRef = useRef<HTMLButtonElement>(null);
  const [pos, setPos] = useState<{ x: number; y: number } | null>(null);

  const mostrar = useCallback(() => {
    const el = anchorRef.current;
    if (!el) return;
    const r = el.getBoundingClientRect();
    setPos({ x: r.left + r.width / 2, y: r.bottom + 8 });
  }, []);

  const ocultar = useCallback(() => setPos(null), []);

  const ajustarAlBorde = useCallback((el: HTMLDivElement | null) => {
    if (!el) return;
    const r = el.getBoundingClientRect();
    const margen = 8;
    let dx = 0;
    if (r.left < margen) dx = margen - r.left;
    else if (r.right > window.innerWidth - margen) dx = window.innerWidth - margen - r.right;
    if (dx) el.style.transform = `translateX(calc(-50% + ${dx}px))`;
  }, []);

  return (
    <>
      <button
        ref={anchorRef}
        type="button"
        className="hover-card"
        onMouseEnter={mostrar}
        onMouseLeave={ocultar}
        onFocus={mostrar}
        onBlur={ocultar}
        onClick={onSeleccionar}
      >
        {titulo}
      </button>
      {pos &&
        createPortal(
          <div
            ref={ajustarAlBorde}
            role="tooltip"
            className="hover-card__ayuda"
            style={{ left: pos.x, top: pos.y, transform: "translateX(-50%)" }}
          >
            {ayuda}
          </div>,
          document.body,
        )}
    </>
  );
}
