import { createContext, useContext, type ReactNode } from "react";

export interface OpcionesConfirmar {
  titulo: string;
  mensaje: ReactNode;
  /** Etiqueta del botón que confirma. Por defecto "Sí". */
  textoOk?: string;
  /** Etiqueta del botón que cancela. Por defecto "No". */
  textoCancelar?: string;
  /** Pinta el header de rojo y el botón de confirmar como destructivo. */
  peligro?: boolean;
  /**
   * Si viene, el botón de confirmar queda deshabilitado hasta que el
   * operario escriba exactamente este texto. Se usa para el borrado de una
   * máquina completa, que no tiene vuelta atrás.
   */
  exigirTexto?: string;
}

export interface OpcionesAviso {
  titulo: string;
  mensaje: ReactNode;
  tipo?: "info" | "aviso" | "error";
}

export interface ApiDialogos {
  /** Diálogo Sí/No. Resuelve en true solo si se confirmó. */
  confirmar: (opciones: OpcionesConfirmar) => Promise<boolean>;
  /** Aviso de una sola salida (equivale a info/warn/error del escritorio). */
  avisar: (opciones: OpcionesAviso) => Promise<void>;
}

export const DialogoContext = createContext<ApiDialogos | null>(null);

export function useDialogos(): ApiDialogos {
  const ctx = useContext(DialogoContext);
  if (!ctx) throw new Error("useDialogos requiere <DialogoProvider> más arriba en el árbol");
  return ctx;
}
