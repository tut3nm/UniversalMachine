import { esNumerico, type Campo } from "./api";

/**
 * Parseo y validación de un valor de campo antes de mandarlo al backend.
 * Es el equivalente de `validacion.parsear_valor_campo` del escritorio
 * (máquina232/src/validacion.py:47): el backend vuelve a validar siempre —
 * esto es para poder avisar en el acto, sin ida y vuelta, igual que la
 * edición en línea de una celda en la app vieja.
 */
export type Parseo = { valor: unknown; error: null } | { valor: null; error: string };

export function parsearValorCampo(campo: Campo, texto: string): Parseo {
  const crudo = texto.trim();

  if (campo.rol === "clave") {
    if (!crudo) return { valor: null, error: `«${campo.titulo_ui}» no puede estar vacío.` };
    return { valor: crudo, error: null };
  }

  if (!esNumerico(campo)) return { valor: crudo, error: null };

  if (crudo === "") return { valor: campo.default ?? 0, error: null };

  const numero = Number(crudo.replace(",", "."));
  if (Number.isNaN(numero)) {
    return { valor: null, error: `«${campo.titulo_ui}» debe ser un número.` };
  }
  const valor = campo.tipo === "decimal" ? numero : Math.round(numero);

  if (campo.min != null && valor < campo.min) {
    return {
      valor: null,
      error: `«${campo.titulo_ui}» debe ser mayor o igual a ${campo.min}.`,
    };
  }
  if (campo.max != null && valor > campo.max) {
    return {
      valor: null,
      error: `«${campo.titulo_ui}» debe ser menor o igual a ${campo.max}.`,
    };
  }
  return { valor, error: null };
}

/** Valor inicial de un campo en el diálogo de alta. */
export function valorPorDefecto(campo: Campo): string {
  if (campo.default != null) return String(campo.default);
  return campo.tipo === "texto" ? "" : "0";
}
