import type { ButtonHTMLAttributes, ReactNode } from "react";
import Tooltip from "./Tooltip";

/**
 * Botón estandarizado de la app — mismo repertorio que `button()` del
 * escritorio (máquina232/src/app.py:139):
 *
 *   primary        acción principal
 *   danger         acción destructiva
 *   secondary      acción neutra frecuente
 *   outline        acción secundaria / utilitaria
 *   outline-danger acción destructiva secundaria
 *   ghost          acción terciaria muy sutil
 *   light          sobre el header de color
 */
export type TipoBoton =
  | "primary"
  | "danger"
  | "secondary"
  | "outline"
  | "outline-danger"
  | "ghost"
  | "light";

interface Props extends ButtonHTMLAttributes<HTMLButtonElement> {
  tipo?: TipoBoton;
  chico?: boolean;
  ancho?: boolean;
  tooltip?: string;
  children: ReactNode;
}

export default function Boton({
  tipo = "secondary",
  chico = false,
  ancho = false,
  tooltip,
  className = "",
  type = "button",
  children,
  ...rest
}: Props) {
  const clases = [
    "ui-btn",
    `ui-btn--${tipo}`,
    chico ? "ui-btn--sm" : "",
    ancho ? "ui-btn--block" : "",
    className,
  ]
    .filter(Boolean)
    .join(" ");

  return (
    <Tooltip texto={tooltip}>
      <button type={type} className={clases} {...rest}>
        {children}
      </button>
    </Tooltip>
  );
}
