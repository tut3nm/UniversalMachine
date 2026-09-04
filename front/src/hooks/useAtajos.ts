import { useEffect, useRef } from "react";

export type Atajos = Record<string, (e: KeyboardEvent) => void>;

const EDITABLES = new Set(["INPUT", "TEXTAREA", "SELECT"]);

function normalizar(e: KeyboardEvent): string {
  const partes: string[] = [];
  if (e.ctrlKey || e.metaKey) partes.push("ctrl");
  if (e.shiftKey) partes.push("shift");
  if (e.altKey) partes.push("alt");
  partes.push(e.key.length === 1 ? e.key.toLowerCase() : e.key);
  return partes.join("+");
}

/**
 * Atajos de teclado de la ventana principal, los mismos que registra
 * `App.__init__` en el escritorio (máquina232/src/app.py:2901):
 *
 *   Ctrl+N nuevo · Ctrl+F buscar · Ctrl+Z deshacer · Ctrl+Y rehacer
 *   Delete eliminar · Enter editar · Escape cancelar
 *
 * Las teclas sueltas (Delete, Enter) se ignoran mientras el foco está en un
 * campo de texto, para no pisar la edición en línea de una celda. Los
 * atajos con Ctrl sí funcionan siempre, igual que en el escritorio.
 */
export function useAtajos(atajos: Atajos, activo = true) {
  // Los handlers se guardan en un ref y se refrescan después de cada
  // render, para que el listener se registre una sola vez y aun así vea
  // siempre el estado más reciente de la pantalla.
  const ref = useRef(atajos);
  useEffect(() => {
    ref.current = atajos;
  });

  useEffect(() => {
    if (!activo) return;
    const onKey = (e: KeyboardEvent) => {
      const handler = ref.current[normalizar(e)];
      if (!handler) return;
      const objetivo = e.target as HTMLElement | null;
      const editando =
        !!objetivo && (EDITABLES.has(objetivo.tagName) || objetivo.isContentEditable);
      const conModificador = e.ctrlKey || e.metaKey;
      if (editando && !conModificador) return;
      e.preventDefault();
      handler(e);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [activo]);
}
