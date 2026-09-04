import { createContext, useContext } from "react";

export type TipoToast = "exito" | "aviso" | "error";

export interface ApiToast {
  /** Notificación breve, no bloqueante, en la esquina (2,6 s). */
  mostrar: (mensaje: string, tipo?: TipoToast) => void;
}

export const ToastContext = createContext<ApiToast | null>(null);

export function useToast(): ApiToast {
  const ctx = useContext(ToastContext);
  if (!ctx) throw new Error("useToast requiere <ToastProvider> más arriba en el árbol");
  return ctx;
}
