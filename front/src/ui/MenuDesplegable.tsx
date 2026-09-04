import { useEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";
import Boton, { type TipoBoton } from "./Boton";

export interface ItemMenu {
  etiqueta: string;
  onSelect: () => void;
  disabled?: boolean;
}

/**
 * Botón que despliega un menú debajo, como el "📤 Exportar ▾" del
 * escritorio (`_show_export_menu`, máquina232/src/app.py:4050).
 */
export default function MenuDesplegable({
  etiqueta,
  items,
  tipo = "secondary",
  tooltip,
  disabled = false,
}: {
  etiqueta: string;
  items: ItemMenu[];
  tipo?: TipoBoton;
  tooltip?: string;
  disabled?: boolean;
}) {
  const [pos, setPos] = useState<{ x: number; y: number } | null>(null);
  const botonRef = useRef<HTMLSpanElement>(null);

  useEffect(() => {
    if (!pos) return;
    const cerrar = () => setPos(null);
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") setPos(null);
    };
    window.addEventListener("mousedown", cerrar);
    window.addEventListener("resize", cerrar);
    window.addEventListener("keydown", onKey);
    return () => {
      window.removeEventListener("mousedown", cerrar);
      window.removeEventListener("resize", cerrar);
      window.removeEventListener("keydown", onKey);
    };
  }, [pos]);

  return (
    <span ref={botonRef} style={{ display: "inline-flex" }}>
      <Boton
        tipo={tipo}
        tooltip={tooltip}
        disabled={disabled}
        onClick={(e) => {
          const r = (e.currentTarget as HTMLElement).getBoundingClientRect();
          setPos((p) => (p ? null : { x: r.left, y: r.bottom + 4 }));
        }}
      >
        {etiqueta}
      </Boton>
      {pos &&
        createPortal(
          <div
            className="ui-menu"
            style={{ left: pos.x, top: pos.y }}
            onMouseDown={(e) => e.stopPropagation()}
            role="menu"
          >
            {items.map((it) => (
              <button
                key={it.etiqueta}
                type="button"
                role="menuitem"
                className="ui-menu__item"
                disabled={it.disabled}
                onClick={() => {
                  setPos(null);
                  it.onSelect();
                }}
              >
                {it.etiqueta}
              </button>
            ))}
          </div>,
          document.body,
        )}
    </span>
  );
}
