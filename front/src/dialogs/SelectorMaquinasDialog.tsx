import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { api, type ResumenMaquina } from "../api";
import { Boton, Modal, useDialogos, useToast } from "../ui";

/**
 * Navegador de documentos de configuración de máquinas. Copia
 * `MachineSelector` del escritorio: una
 * tarjeta por máquina, la actual marcada, `➕ Agregar máquina` a la
 * izquierda del footer y `🗑 Eliminar` a la derecha. El borrado pide
 * confirmación tipeando el nombre completo de la máquina (decisión tomada
 * con el usuario: la web es más estricta que el `confirm()` del
 * escritorio para esta acción irreversible).
 */
export default function SelectorMaquinasDialog({
  currentId,
  onElegir,
  onAgregarMaquina,
  onCerrar,
}: {
  currentId?: string;
  onElegir: (id: string) => void;
  onAgregarMaquina: () => void;
  onCerrar: () => void;
}) {
  const navigate = useNavigate();
  const { confirmar, avisar } = useDialogos();
  const toast = useToast();
  const [maquinas, setMaquinas] = useState<ResumenMaquina[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [eliminando, setEliminando] = useState<string | null>(null);

  const cargar = () => {
    api
      .listarMaquinas()
      .then(setMaquinas)
      .catch((e) => setError(String(e)));
  };

  useEffect(cargar, []);

  const onEliminar = async (m: ResumenMaquina) => {
    setEliminando(m.id);
    try {
      const ok = await confirmar({
        titulo: "Eliminar máquina",
        mensaje:
          `¿Eliminar permanentemente la máquina «${m.nombre}»?\n\n` +
          `Se borrarán el perfil y todos sus datos y metadatos.\n\n` +
          "Esta acción no se puede deshacer.",
        peligro: true,
        textoOk: "Confirmar eliminación",
        textoCancelar: "Cancelar",
        exigirTexto: m.nombre,
      });
      if (!ok) return;
      await api.eliminarMaquina(m.id, m.nombre);
      toast.mostrar(`Máquina «${m.nombre}» eliminada.`, "aviso");
      if (m.id === currentId) navigate("/");
      cargar();
    } catch (e) {
      await avisar({ titulo: "No se pudo eliminar", mensaje: String(e), tipo: "error" });
    } finally {
      setEliminando(null);
    }
  };

  return (
    <Modal
      titulo="Documentos de configuración de máquinas"
      ancho={640}
      onCerrar={onCerrar}
      ayuda="Elegí qué máquina administrar. Cada una guarda sus propios datos y no se mezclan entre sí."
      footer={
        <>
          <Boton tipo="primary" onClick={onAgregarMaquina}>
            ➕ Agregar máquina
          </Boton>
          <span className="ui-modal__footer-sep" />
          <Boton tipo="secondary" onClick={onCerrar}>
            Cerrar
          </Boton>
        </>
      }
    >
      {error && <p className="error">{error}</p>}
      {!maquinas ? (
        <p className="muted">Cargando…</p>
      ) : maquinas.length === 0 ? (
        <p className="muted">Todavía no hay ninguna máquina configurada.</p>
      ) : (
        maquinas.map((m) => {
          const esActual = m.id === currentId;
          return (
            <div className={"sel-card" + (esActual ? " sel-card--actual" : "")} key={m.id}>
              <button
                type="button"
                className="sel-card-cuerpo"
                onClick={() => onElegir(m.id)}
              >
                <span className="sel-card-nombre">{m.nombre}</span>
                {esActual && <span className="sel-card-etiqueta">● máquina actual</span>}
              </button>
              <Boton
                tipo="danger"
                chico
                disabled={eliminando !== null}
                onClick={() => void onEliminar(m)}
                tooltip="Eliminar esta máquina y sus datos"
              >
                🗑 Eliminar
              </Boton>
            </div>
          );
        })
      )}
    </Modal>
  );
}
