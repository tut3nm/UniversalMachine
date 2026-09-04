import type { Hallazgo } from "../api";
import { Boton, Modal } from "../ui";

const TIPO_HALLAZGO_LABEL: Record<string, string> = {
  fuera_de_rango: "Fuera de rango",
  campo_vacio: "Campo vacío",
  duplicado: "Posible duplicado",
};

/**
 * Todos los problemas del catálogo en una sola lista: valores fuera de
 * rango, campos obligatorios vacíos y duplicados sin revisar, más cuántos
 * slots vacíos quedan libres. Copia `SaludDialog` del escritorio
 * (máquina232/src/app.py:2434), con "Ir al registro" reemplazado por poner
 * su código en la búsqueda de la tabla (acá no hay una fila física a la
 * que hacer scroll: la tabla es virtualizada y pide del servidor).
 */
export default function SaludDialog({
  hallazgos,
  slotsLibres,
  onIrAlRegistro,
  onCerrar,
}: {
  hallazgos: Hallazgo[];
  slotsLibres: number;
  onIrAlRegistro: (code: string) => void;
  onCerrar: () => void;
}) {
  return (
    <Modal
      titulo="Salud del catálogo"
      ancho={680}
      onCerrar={onCerrar}
      ayuda={`${hallazgos.length} hallazgo(s) · ${slotsLibres} slot(s) libre(s)`}
      footer={
        <>
          <span className="ui-modal__footer-sep" />
          <Boton tipo="secondary" onClick={onCerrar}>
            Cerrar
          </Boton>
        </>
      }
    >
      {hallazgos.length === 0 ? (
        <p style={{ color: "var(--success)", fontWeight: 600 }}>
          ✓ No se encontraron problemas en el catálogo.
        </p>
      ) : (
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>Tipo</th>
                <th>Código</th>
                <th>Detalle</th>
                <th />
              </tr>
            </thead>
            <tbody>
              {hallazgos.map((h, i) => (
                <tr key={`${h.tipo}-${h.code}-${i}`}>
                  <td>{TIPO_HALLAZGO_LABEL[h.tipo] ?? h.tipo}</td>
                  <td>{h.code}</td>
                  <td>{h.mensaje}</td>
                  <td>
                    <Boton
                      tipo="ghost"
                      chico
                      onClick={() => onIrAlRegistro(h.code)}
                      tooltip="Buscar este registro en la tabla"
                    >
                      Ir al registro
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
