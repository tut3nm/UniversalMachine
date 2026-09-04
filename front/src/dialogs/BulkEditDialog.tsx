import { useState } from "react";
import type { Campo } from "../api";
import { Boton, Modal, useDialogos } from "../ui";
import { parsearValorCampo } from "../validacion";

/**
 * Aplica el mismo valor a un parámetro de todos los registros seleccionados
 * de una vez. Copia `BulkEditDialog` del escritorio
 * (máquina232/src/app.py:2673): combo de campo, valor nuevo, confirmación
 * antes de aplicar y el botón etiquetado con la cantidad.
 */
export default function BulkEditDialog({
  campos,
  cantidad,
  onAplicar,
  onCerrar,
}: {
  /** Solo parámetros (nunca la clave): igual que `parametros_visibles()`. */
  campos: Campo[];
  cantidad: number;
  onAplicar: (campo: Campo, texto: string) => Promise<string | void>;
  onCerrar: () => void;
}) {
  const { confirmar } = useDialogos();
  const [nombreCampo, setNombreCampo] = useState(campos[0]?.nombre_interno ?? "");
  const [texto, setTexto] = useState("");
  const [problema, setProblema] = useState<string | null>(null);
  const [aplicando, setAplicando] = useState(false);

  const campo = campos.find((c) => c.nombre_interno === nombreCampo) ?? campos[0];

  const aceptar = async () => {
    if (!campo) return;
    const parseo = parsearValorCampo(campo, texto);
    if (parseo.error) {
      setProblema(parseo.error);
      return;
    }
    const ok = await confirmar({
      titulo: "Confirmar edición masiva",
      mensaje: `¿Poner «${campo.titulo_ui}» = ${parseo.valor} en ${cantidad} registro(s)?`,
    });
    if (!ok) return;

    setProblema(null);
    setAplicando(true);
    const error = await onAplicar(campo, texto);
    setAplicando(false);
    if (error) setProblema(error);
  };

  return (
    <Modal
      titulo="Editar en masa"
      ancho={460}
      onCerrar={onCerrar}
      ayuda={`Se va a aplicar el mismo valor a los ${cantidad} registro(s) seleccionados.`}
      footer={
        <>
          <span className="ui-modal__footer-sep" />
          <Boton tipo="secondary" onClick={onCerrar} disabled={aplicando}>
            Cancelar
          </Boton>
          <Boton tipo="primary" onClick={() => void aceptar()} disabled={aplicando || !campo}>
            {aplicando ? "Aplicando…" : `Aplicar a ${cantidad}`}
          </Boton>
        </>
      }
    >
      {problema && <p className="error">{problema}</p>}
      <div className="reg-campo">
        <label htmlFor="bulk-campo">Campo</label>
        <select
          id="bulk-campo"
          value={nombreCampo}
          onChange={(e) => setNombreCampo(e.target.value)}
        >
          {campos.map((c) => (
            <option key={c.nombre_interno} value={c.nombre_interno}>
              {c.titulo_ui}
            </option>
          ))}
        </select>
      </div>
      <div className="reg-campo">
        <label htmlFor="bulk-valor">Valor nuevo</label>
        <input
          id="bulk-valor"
          value={texto}
          autoComplete="off"
          autoFocus
          onChange={(e) => setTexto(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter") {
              e.preventDefault();
              void aceptar();
            }
          }}
        />
      </div>
    </Modal>
  );
}
