import { useEffect, useState } from "react";
import { api, type Campo, type DuplicadoGrupo, type DuplicadoRegistro } from "../api";
import { Boton, Modal, useDialogos, useToast } from "../ui";

function textoFila(r: DuplicadoRegistro, parametros: Campo[]): string {
  const partes = [r.code, ...parametros.map((c) => `${c.titulo_ui} ${r.valores[c.nombre_interno] ?? ""}`)];
  return partes.join("   ·   ");
}

/**
 * Códigos con posible duplicado, agrupados por firma (según el método de
 * duplicados del perfil). Copia `DuplicatesDialog` del escritorio: una
 * tarjeta por grupo, "Copiar código" para
 * buscarlo en SAP, "No es duplicado" para descartarlo de esta búsqueda de
 * forma permanente, y borrado con preview de hasta 6 códigos.
 */
export default function DuplicadosDialog({
  machineId,
  parametros,
  onEliminados,
  onCerrar,
}: {
  machineId: string;
  /** Parámetros visibles del perfil, para armar el texto de cada fila. */
  parametros: Campo[];
  onEliminados: (hash: string) => void;
  onCerrar: () => void;
}) {
  const { confirmar, avisar } = useDialogos();
  const toast = useToast();
  const [grupos, setGrupos] = useState<DuplicadoGrupo[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [seleccion, setSeleccion] = useState<Set<number>>(new Set());
  const [revisados, setRevisados] = useState<Set<string>>(new Set());
  const [aplicando, setAplicando] = useState(false);

  const cargar = () => {
    api
      .listarDuplicados(machineId)
      .then((r) => setGrupos(r.grupos))
      .catch((e) => setError(String(e)));
  };

  useEffect(cargar, [machineId]);

  const alternar = (index: number) =>
    setSeleccion((s) => {
      const n = new Set(s);
      if (n.has(index)) n.delete(index);
      else n.add(index);
      return n;
    });

  const copiarCodigo = async (code: string) => {
    try {
      await navigator.clipboard.writeText(code);
      toast.mostrar(`Código «${code}» copiado al portapapeles.`);
    } catch {
      await avisar({
        titulo: "No se pudo copiar",
        mensaje: "El navegador no permitió copiar al portapapeles.",
        tipo: "error",
      });
    }
  };

  const marcarNoDuplicado = async (code: string, index: number) => {
    try {
      await api.marcarNoDuplicado(machineId, code);
      setRevisados((r) => new Set(r).add(code));
      setSeleccion((s) => {
        const n = new Set(s);
        n.delete(index);
        return n;
      });
    } catch (e) {
      await avisar({ titulo: "No se pudo marcar", mensaje: String(e), tipo: "error" });
    }
  };

  const onEliminarSeleccionados = async () => {
    if (seleccion.size === 0) {
      await avisar({ titulo: "Sin selección", mensaje: "No marcaste ningún registro para eliminar." });
      return;
    }
    const indices = [...seleccion];
    const porIndice = new Map(
      (grupos ?? []).flatMap((g) => g.registros).map((r) => [r.index, r.code]),
    );
    const codigos = indices.map((i) => porIndice.get(i) ?? `#${i}`);
    const preview = codigos.slice(0, 6).join(", ") + (codigos.length > 6 ? " …" : "");
    const ok = await confirmar({
      titulo: "Confirmar eliminación",
      mensaje: `¿Eliminar ${indices.length} registro(s) marcados como duplicados?\n\n${preview}`,
      peligro: true,
      textoOk: "Eliminar",
      textoCancelar: "Cancelar",
    });
    if (!ok) return;
    setAplicando(true);
    try {
      const r = await api.eliminarDuplicados(machineId, indices);
      onEliminados(r.hash);
      toast.mostrar(`${r.eliminados} registro(s) eliminado(s).`, "aviso");
      setSeleccion(new Set());
      cargar();
    } catch (e) {
      await avisar({ titulo: "No se pudieron eliminar", mensaje: String(e), tipo: "error" });
    } finally {
      setAplicando(false);
    }
  };

  const nGrupos = grupos?.length ?? 0;
  const nRegistros = grupos?.reduce((n, g) => n + g.registros.length, 0) ?? 0;

  return (
    <Modal
      titulo="Posibles duplicados"
      ancho={780}
      onCerrar={onCerrar}
      ayuda={
        !grupos
          ? undefined
          : nGrupos
            ? `${nGrupos} grupo(s) con ${nRegistros} registro(s) con códigos parecidos. Copiá el ` +
              'código para buscarlo en SAP; marcá "Eliminar" si es duplicado real, o "No es ' +
              'duplicado" para descartarlo de esta búsqueda.'
            : "No se encontraron códigos con posible duplicado."
      }
      footer={
        <>
          <span className="ui-modal__footer-sep" />
          <Boton tipo="secondary" onClick={onCerrar}>
            Cerrar
          </Boton>
          <Boton
            tipo="danger"
            disabled={aplicando || nGrupos === 0}
            onClick={() => void onEliminarSeleccionados()}
          >
            Eliminar seleccionados
          </Boton>
        </>
      }
    >
      {error && <p className="error">{error}</p>}
      {!grupos ? (
        <p className="muted">Cargando…</p>
      ) : (
        grupos.map((g, gi) => (
          <div className="dup-grupo" key={gi}>
            <p className="dup-grupo-titulo">Grupo {gi + 1}</p>
            {g.registros.map((r) => {
              const marcado = revisados.has(r.code);
              return (
                <div className={"dup-fila" + (marcado ? " dup-fila--revisado" : "")} key={r.index}>
                  <input
                    type="checkbox"
                    checked={seleccion.has(r.index)}
                    disabled={marcado}
                    onChange={() => alternar(r.index)}
                  />
                  <span className="dup-texto">{textoFila(r, parametros)}</span>
                  <Boton
                    tipo="outline"
                    chico
                    disabled={marcado}
                    onClick={() => void copiarCodigo(r.code)}
                    tooltip="Copiar al portapapeles para buscarlo en SAP."
                  >
                    Copiar código
                  </Boton>
                  <Boton
                    tipo="secondary"
                    chico
                    disabled={marcado}
                    onClick={() => void marcarNoDuplicado(r.code, r.index)}
                    tooltip="Marcar como revisado: no vuelve a aparecer en futuras búsquedas de duplicados."
                  >
                    {marcado ? "Marcado: no es duplicado" : "No es duplicado"}
                  </Boton>
                </div>
              );
            })}
          </div>
        ))
      )}
    </Modal>
  );
}
