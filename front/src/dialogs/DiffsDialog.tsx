import { useEffect, useMemo, useState } from "react";
import { api, TIPO_DIFF_LABEL, type Campo, type DiffRegistro } from "../api";
import { Boton, Modal, useDialogos } from "../ui";

const TIPOS: DiffRegistro["tipo"][] = ["alta", "baja", "modificacion"];

function queCambio(d: DiffRegistro, titulosPorCampo: Record<string, string>): string {
  if (d.tipo !== "modificacion") return "";
  return d.campos_modificados.map((c) => titulosPorCampo[c] ?? c).join(", ");
}

function detalleDe(d: DiffRegistro, titulosPorCampo: Record<string, string>): string {
  if (d.tipo === "alta") {
    return Object.entries(d.nuevos ?? {})
      .map(([c, v]) => `${titulosPorCampo[c] ?? c}: ${v}`)
      .join("\n");
  }
  if (d.tipo === "baja") {
    return Object.entries(d.anteriores ?? {})
      .map(([c, v]) => `${titulosPorCampo[c] ?? c}: ${v}`)
      .join("\n");
  }
  return d.campos_modificados
    .map((c) => `${titulosPorCampo[c] ?? c}: ${d.anteriores?.[c]} → ${d.nuevos?.[c]}`)
    .join("\n");
}

/**
 * Comparación entre el archivo actual y el original. Copia `DiffsDialog`
 * del escritorio: tres checkboxes de tipo,
 * tabla con lo que cambió, y exportación del informe en CSV (solo lo que
 * queda visible con los checkboxes, igual que allá).
 */
export default function DiffsDialog({
  machineId,
  campos,
  onCerrar,
}: {
  machineId: string;
  campos: Campo[];
  onCerrar: () => void;
}) {
  const { avisar } = useDialogos();
  const [diffs, setDiffs] = useState<DiffRegistro[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [tiposActivos, setTiposActivos] = useState<Set<string>>(new Set(TIPOS));
  const [seleccionado, setSeleccionado] = useState<DiffRegistro | null>(null);

  const titulosPorCampo = useMemo(
    () => Object.fromEntries(campos.map((c) => [c.nombre_interno, c.titulo_ui])),
    [campos],
  );

  useEffect(() => {
    api
      .diferencias(machineId)
      .then((r) => setDiffs(r.diffs))
      .catch((e) => setError(String(e)));
  }, [machineId]);

  const conteos = useMemo(() => {
    const c = { alta: 0, baja: 0, modificacion: 0 };
    for (const d of diffs ?? []) c[d.tipo]++;
    return c;
  }, [diffs]);

  const filtrados = useMemo(
    () => (diffs ?? []).filter((d) => tiposActivos.has(d.tipo)),
    [diffs, tiposActivos],
  );

  const alternarTipo = (tipo: string) =>
    setTiposActivos((s) => {
      const n = new Set(s);
      if (n.has(tipo)) n.delete(tipo);
      else n.add(tipo);
      return n;
    });

  const verDetalle = async (d: DiffRegistro) => {
    await avisar({
      titulo: `${TIPO_DIFF_LABEL[d.tipo]} — ${d.code}`,
      mensaje: detalleDe(d, titulosPorCampo) || "(sin campos)",
    });
  };

  const onExportar = () => {
    if (filtrados.length === 0) {
      void avisar({ titulo: "Exportar informe", mensaje: "Nada para exportar." });
      return;
    }
    window.open(api.diferenciasInformeCsvUrl(machineId, [...tiposActivos]), "_blank");
  };

  const resumen = diffs && diffs.length
    ? `${conteos.alta} alta(s) · ${conteos.baja} baja(s) · ${conteos.modificacion} modificación(es)`
    : "No hay diferencias con el archivo original.";

  return (
    <Modal
      titulo="Ver cambios contra el original"
      ancho={760}
      onCerrar={onCerrar}
      footer={
        <>
          <Boton tipo="outline" onClick={onExportar}>
            Exportar informe (CSV)…
          </Boton>
          <span className="ui-modal__footer-sep" />
          <Boton
            tipo="outline"
            disabled={!seleccionado}
            onClick={() => seleccionado && void verDetalle(seleccionado)}
          >
            Ver detalle
          </Boton>
          <Boton tipo="secondary" onClick={onCerrar}>
            Cerrar
          </Boton>
        </>
      }
    >
      {error && <p className="error">{error}</p>}
      {!diffs ? (
        <p className="muted">Cargando…</p>
      ) : (
        <>
          <p className="diff-resumen">{resumen}</p>

          {diffs.length > 0 && (
            <div className="diff-tipos">
              {TIPOS.map((t) => (
                <label key={t} className={`diff-${t}`}>
                  <input
                    type="checkbox"
                    checked={tiposActivos.has(t)}
                    onChange={() => alternarTipo(t)}
                  />
                  {TIPO_DIFF_LABEL[t]} ({conteos[t]})
                </label>
              ))}
            </div>
          )}

          {diffs.length > 0 && (
            <div className="table-wrap">
              <table>
                <thead>
                  <tr>
                    <th>Tipo</th>
                    <th>Código</th>
                    <th>Qué cambió</th>
                  </tr>
                </thead>
                <tbody>
                  {filtrados.map((d) => (
                    <tr
                      key={`${d.tipo}-${d.code}`}
                      className={
                        `tabla-fila-clic diff-${d.tipo}` +
                        (seleccionado === d ? " fila-seleccionada" : "")
                      }
                      onClick={() => setSeleccionado(d)}
                      onDoubleClick={() => void verDetalle(d)}
                    >
                      <td>{TIPO_DIFF_LABEL[d.tipo]}</td>
                      <td>{d.code}</td>
                      <td>{queCambio(d, titulosPorCampo)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </>
      )}
    </Modal>
  );
}
