import { useCallback, useMemo, useRef, useState, type ReactNode } from "react";
import { createPortal } from "react-dom";
import { ToastContext, type TipoToast } from "./toastContext";

const DURACION_MS = 2600; // igual que ToastNotification en el escritorio

interface Aviso {
  id: number;
  mensaje: string;
  tipo: TipoToast;
}

/**
 * Notificaciones breves en la esquina, para confirmar que una acción se
 * completó sin interrumpir al operario con un diálogo modal. Equivale a
 * `toast()` en máquina232/src/app.py:255.
 */
export default function ToastProvider({ children }: { children: ReactNode }) {
  const [avisos, setAvisos] = useState<Aviso[]>([]);
  const proximoId = useRef(1);

  const mostrar = useCallback((mensaje: string, tipo: TipoToast = "exito") => {
    const id = proximoId.current++;
    setAvisos((prev) => [...prev, { id, mensaje, tipo }]);
    window.setTimeout(
      () => setAvisos((prev) => prev.filter((a) => a.id !== id)),
      DURACION_MS,
    );
  }, []);

  const api = useMemo(() => ({ mostrar }), [mostrar]);

  return (
    <ToastContext.Provider value={api}>
      {children}
      {createPortal(
        <div className="ui-toasts" aria-live="polite">
          {avisos.map((a) => (
            <div key={a.id} className={`ui-toast ui-toast--${a.tipo}`}>
              <div className="ui-toast__titulo">Configurador de Planta</div>
              {a.mensaje}
            </div>
          ))}
        </div>,
        document.body,
      )}
    </ToastContext.Provider>
  );
}
