import { useCallback, useMemo, useState, type ReactNode } from "react";
import Boton from "./Boton";
import Modal from "./Modal";
import {
  DialogoContext,
  type OpcionesAviso,
  type OpcionesConfirmar,
} from "./dialogoContext";

type Pendiente =
  | { clase: "confirmar"; opciones: OpcionesConfirmar; resolver: (v: boolean) => void }
  | { clase: "aviso"; opciones: OpcionesAviso; resolver: () => void };

/**
 * Diálogos de confirmación y de aviso, con las etiquetas fijas en español
 * (Sí/No), igual que `confirm()`, `info()`, `warn()` y `error()` del
 * escritorio (máquina232/src/app.py:225-253). Se exponen como promesas para
 * poder escribirlos en línea dentro de un handler `async`.
 */
export default function DialogoProvider({ children }: { children: ReactNode }) {
  const [pendiente, setPendiente] = useState<Pendiente | null>(null);
  const [textoTipeado, setTextoTipeado] = useState("");

  const cerrar = useCallback(() => {
    setPendiente(null);
    setTextoTipeado("");
  }, []);

  const confirmar = useCallback(
    (opciones: OpcionesConfirmar) =>
      new Promise<boolean>((resolver) => {
        setTextoTipeado("");
        setPendiente({ clase: "confirmar", opciones, resolver });
      }),
    [],
  );

  const avisar = useCallback(
    (opciones: OpcionesAviso) =>
      new Promise<void>((resolver) => {
        setPendiente({ clase: "aviso", opciones, resolver });
      }),
    [],
  );

  const api = useMemo(() => ({ confirmar, avisar }), [confirmar, avisar]);

  const responder = (valor: boolean) => {
    if (!pendiente) return;
    if (pendiente.clase === "confirmar") pendiente.resolver(valor);
    else pendiente.resolver();
    cerrar();
  };

  let modal: ReactNode = null;
  if (pendiente?.clase === "confirmar") {
    const o = pendiente.opciones;
    const bloqueado = o.exigirTexto !== undefined && textoTipeado.trim() !== o.exigirTexto;
    modal = (
      <Modal
        titulo={o.titulo}
        ancho={520}
        peligro={o.peligro}
        onCerrar={() => responder(false)}
        footer={
          <>
            <span className="ui-modal__footer-sep" />
            <Boton tipo="secondary" onClick={() => responder(false)}>
              {o.textoCancelar ?? "No"}
            </Boton>
            <Boton
              tipo={o.peligro ? "danger" : "primary"}
              disabled={bloqueado}
              onClick={() => responder(true)}
            >
              {o.textoOk ?? "Sí"}
            </Boton>
          </>
        }
      >
        <div className="dlg-mensaje">{o.mensaje}</div>
        {o.exigirTexto !== undefined && (
          <label className="dlg-tipeo">
            Para confirmar, escribí <strong>{o.exigirTexto}</strong>
            <input
              value={textoTipeado}
              onChange={(e) => setTextoTipeado(e.target.value)}
              autoComplete="off"
            />
          </label>
        )}
      </Modal>
    );
  } else if (pendiente?.clase === "aviso") {
    const o = pendiente.opciones;
    modal = (
      <Modal
        titulo={o.titulo}
        ancho={520}
        peligro={o.tipo === "error"}
        onCerrar={() => responder(true)}
        footer={
          <>
            <span className="ui-modal__footer-sep" />
            <Boton tipo="primary" onClick={() => responder(true)}>
              Entendido
            </Boton>
          </>
        }
      >
        <div className="dlg-mensaje">{o.mensaje}</div>
      </Modal>
    );
  }

  return (
    <DialogoContext.Provider value={api}>
      {children}
      {modal}
    </DialogoContext.Provider>
  );
}
