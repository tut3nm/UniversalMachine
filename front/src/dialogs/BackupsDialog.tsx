import { useEffect, useState } from "react";
import { api, type BackupInfo } from "../api";
import { Boton, Modal, useDialogos, useToast } from "../ui";

function previa(codigos: string[], max = 6): string {
  const cortado = codigos.slice(0, max).join(", ");
  return codigos.length > max ? `${cortado} …` : cortado;
}

/**
 * Puntos de respaldo automáticos, uno por cada guardado. Copia
 * `BackupsDialog` del escritorio: una tarjeta
 * por backup con fecha, tamaño y aviso si el hash no verifica, y — antes de
 * restaurar — un resumen de impacto (qué se perdería, qué se recuperaría,
 * qué cambiaría) que el operario tiene que confirmar.
 */
export default function BackupsDialog({
  machineId,
  onRestaurado,
  onCerrar,
}: {
  machineId: string;
  /** Se llama tras restaurar con éxito, con el hash nuevo del archivo. */
  onRestaurado: (hash: string) => void;
  onCerrar: () => void;
}) {
  const { confirmar, avisar } = useDialogos();
  const toast = useToast();
  const [backups, setBackups] = useState<BackupInfo[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [restaurando, setRestaurando] = useState<string | null>(null);

  const cargar = () => {
    api
      .listarBackups(machineId)
      .then(setBackups)
      .catch((e) => setError(String(e)));
  };

  useEffect(cargar, [machineId]);

  const onRestaurar = async (b: BackupInfo) => {
    const fecha = new Date(b.timestamp).toLocaleString();
    setRestaurando(b.nombre);
    try {
      const preview = await api.backupPreview(machineId, b.nombre);
      const partes: string[] = [];
      if (preview.se_perderian.length)
        partes.push(
          `${preview.se_perderian.length} registro(s) que hoy existen se PERDERÍAN: ${previa(preview.se_perderian)}`,
        );
      if (preview.se_recuperarian.length)
        partes.push(
          `${preview.se_recuperarian.length} registro(s) borrados se RECUPERARÍAN: ${previa(preview.se_recuperarian)}`,
        );
      if (preview.cambiarian.length)
        partes.push(
          `${preview.cambiarian.length} registro(s) CAMBIARÍAN de valor: ${previa(preview.cambiarian)}`,
        );
      const mensaje = partes.length
        ? partes.join("\n\n")
        : "No hay diferencias entre el estado actual y este backup.";
      const advertencia = preview.integridad_ok
        ? ""
        : "\n\n⚠ Este backup no pasa la verificación de integridad (hash): puede estar dañado o alterado.";

      const ok = await confirmar({
        titulo: `Restaurar el backup del ${fecha}`,
        mensaje: mensaje + advertencia,
        peligro: true,
        textoOk: "Restaurar",
        textoCancelar: "Cancelar",
      });
      if (!ok) return;

      const r = await api.restaurarBackup(machineId, b.nombre);
      onRestaurado(r.hash);
      toast.mostrar("Backup restaurado.", "aviso");
      cargar();
    } catch (e) {
      await avisar({ titulo: "No se pudo restaurar el backup", mensaje: String(e), tipo: "error" });
    } finally {
      setRestaurando(null);
    }
  };

  return (
    <Modal
      titulo="Backups"
      ancho={640}
      onCerrar={onCerrar}
      ayuda="Se crea uno automáticamente antes de cada guardado."
      footer={
        <>
          <span className="ui-modal__footer-sep" />
          <Boton tipo="secondary" onClick={onCerrar}>
            Cerrar
          </Boton>
        </>
      }
    >
      {error && <p className="error">{error}</p>}
      {!backups ? (
        <p className="muted">Cargando…</p>
      ) : backups.length === 0 ? (
        <p className="muted">Todavía no hay ningún respaldo.</p>
      ) : (
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>Fecha</th>
                <th>Tamaño</th>
                <th></th>
              </tr>
            </thead>
            <tbody>
              {backups.map((b) => (
                <tr key={b.nombre} className={b.integridad_ok ? "" : "fila-alerta"}>
                  <td>
                    {new Date(b.timestamp).toLocaleString()}
                    {!b.integridad_ok && (
                      <>
                        <br />
                        <span className="error">⚠ hash no verificado</span>
                      </>
                    )}
                  </td>
                  <td className="muted">{(b.tamano_bytes / 1024).toFixed(1)} KB</td>
                  <td>
                    <Boton
                      tipo="outline-danger"
                      chico
                      disabled={restaurando !== null}
                      onClick={() => void onRestaurar(b)}
                    >
                      Restaurar este backup
                    </Boton>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </Modal>
  );
}
