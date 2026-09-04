import { useMemo, useState } from "react";
import { esNumerico, type Campo, type Registro } from "../api";
import { Boton, Modal } from "../ui";
import { parsearValorCampo, valorPorDefecto } from "../validacion";

/**
 * Alta y edición de un registro, con un campo por campo visible del perfil.
 * Copia `RecordDialog` del escritorio (máquina232/src/app.py:1287): etiqueta
 * en negrita arriba, ayuda a la derecha, spinbox cuando el campo es entero
 * con mínimo y máximo, y las mismas validaciones antes de aceptar.
 */
function ayudaDe(campo: Campo): string {
  if (campo.rol === "clave") return "identificador único";
  if (campo.min != null && campo.max != null) return `${campo.min} a ${campo.max}`;
  if (esNumerico(campo)) return "número";
  return "";
}

export default function RegistroDialog({
  titulo,
  campos,
  registro = null,
  onGuardar,
  onCerrar,
}: {
  titulo: string;
  campos: Campo[];
  registro?: Registro | null;
  /** Undefined/void en éxito (el padre cierra el diálogo); un string deja
   *  el diálogo abierto y lo muestra como error — así una clave duplicada
   *  o un conflicto de guardado se ven en el mismo lugar que un error de
   *  parseo local, sin perder lo que el operario ya tipeó. */
  onGuardar: (valores: Record<string, unknown>) => Promise<string | void>;
  onCerrar: () => void;
}) {
  const inicial = useMemo(() => {
    const v: Record<string, string> = {};
    for (const c of campos) {
      v[c.nombre_interno] = registro
        ? String(registro[c.nombre_interno] ?? "")
        : valorPorDefecto(c);
    }
    return v;
  }, [campos, registro]);

  const [valores, setValores] = useState<Record<string, string>>(inicial);
  const [problema, setProblema] = useState<string | null>(null);
  const [guardando, setGuardando] = useState(false);

  const aceptar = async () => {
    const salida: Record<string, unknown> = {};
    for (const campo of campos) {
      const parseo = parsearValorCampo(campo, valores[campo.nombre_interno] ?? "");
      if (parseo.error) {
        setProblema(parseo.error);
        return;
      }
      salida[campo.nombre_interno] = parseo.valor;
    }
    setProblema(null);
    setGuardando(true);
    const error = await onGuardar(salida);
    setGuardando(false);
    if (error) setProblema(error);
  };

  return (
    <Modal
      titulo={titulo}
      ancho={560}
      onCerrar={onCerrar}
      footer={
        <>
          <span className="ui-modal__footer-sep" />
          <Boton tipo="secondary" onClick={onCerrar} disabled={guardando}>
            Cancelar
          </Boton>
          <Boton tipo="primary" onClick={() => void aceptar()} disabled={guardando}>
            {guardando ? "Guardando…" : "Guardar"}
          </Boton>
        </>
      }
    >
      {problema && <p className="error">{problema}</p>}
      <form
        className="reg-form"
        onSubmit={(e) => {
          e.preventDefault();
          void aceptar();
        }}
      >
        {campos.map((campo) => {
          const ayuda = ayudaDe(campo);
          const spin = campo.tipo === "entero" && campo.min != null && campo.max != null;
          return (
            <div className="reg-campo" key={campo.nombre_interno}>
              <label htmlFor={`campo-${campo.nombre_interno}`}>{campo.titulo_ui}</label>
              <div className="reg-entrada">
                <input
                  id={`campo-${campo.nombre_interno}`}
                  type={spin ? "number" : "text"}
                  min={spin ? campo.min ?? undefined : undefined}
                  max={spin ? campo.max ?? undefined : undefined}
                  value={valores[campo.nombre_interno] ?? ""}
                  autoComplete="off"
                  onChange={(e) =>
                    setValores((v) => ({ ...v, [campo.nombre_interno]: e.target.value }))
                  }
                />
                {ayuda && <span className="reg-ayuda">{ayuda}</span>}
              </div>
            </div>
          );
        })}
        {/* Permite que Enter envíe el formulario sin un botón visible extra. */}
        <button type="submit" hidden />
      </form>
    </Modal>
  );
}
