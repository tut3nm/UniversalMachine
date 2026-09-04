import { useCallback, useEffect, useState } from "react";
import { api, rangosDeFiltroAStrings, type Campo, type FiltroGuardado } from "../api";
import { Boton, Modal, useDialogos } from "../ui";

type Extremos = { min: string; max: string };

function rangosIniciales(campos: Campo[], crudos: string[]): Record<string, Extremos> {
  const mapa: Record<string, Extremos> = {};
  for (const c of campos) mapa[c.nombre_interno] = { min: "", max: "" };
  for (const crudo of crudos) {
    const [campo, min, max] = crudo.split(":");
    if (campo in mapa) mapa[campo] = { min: min ?? "", max: max ?? "" };
  }
  return mapa;
}

/**
 * Filtros de rango numérico por campo, más presets de "búsqueda + rangos"
 * guardados por máquina. Copia `FiltrosDialog` del escritorio
 * (máquina232/src/app.py:2521): una fila por campo numérico, Limpiar
 * (aplica y deja el diálogo abierto), Guardar como… y Aplicar (aplica y
 * cierra), y la lista de presets con Aplicar/Eliminar cada uno.
 */
export default function FiltrosDialog({
  machineId,
  campos,
  rangosActuales,
  busquedaActual,
  onAplicar,
  onAplicarPreset,
  onCerrar,
}: {
  machineId: string;
  /** Solo parámetros numéricos visibles. */
  campos: Campo[];
  rangosActuales: string[];
  busquedaActual: string;
  onAplicar: (rangos: string[]) => void;
  onAplicarPreset: (busqueda: string, rangos: string[]) => void;
  onCerrar: () => void;
}) {
  const { avisar } = useDialogos();
  const [filas, setFilas] = useState<Record<string, Extremos>>(() =>
    rangosIniciales(campos, rangosActuales),
  );
  const [presets, setPresets] = useState<FiltroGuardado[] | null>(null);
  const [mostrarGuardar, setMostrarGuardar] = useState(false);
  const [nombreNuevo, setNombreNuevo] = useState("");
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api
      .listarFiltros(machineId)
      .then(setPresets)
      .catch((e) => setError(String(e)));
  }, [machineId]);

  const leerRangos = useCallback(
    (): string[] =>
      campos
        .map((c) => {
          const { min, max } = filas[c.nombre_interno] ?? { min: "", max: "" };
          if (!min.trim() && !max.trim()) return null;
          return `${c.nombre_interno}:${min.trim()}:${max.trim()}`;
        })
        .filter((r): r is string => r !== null),
    [campos, filas],
  );

  const onLimpiar = () => {
    setFilas(rangosIniciales(campos, []));
    onAplicar([]);
  };

  const onAceptarAplicar = () => {
    onAplicar(leerRangos());
    onCerrar();
  };

  const onGuardarComo = async () => {
    if (!nombreNuevo.trim()) return;
    try {
      const actualizados = await api.guardarFiltro(
        machineId,
        nombreNuevo.trim(),
        busquedaActual,
        leerRangos(),
      );
      setPresets(actualizados);
      setMostrarGuardar(false);
      setNombreNuevo("");
    } catch (e) {
      await avisar({ titulo: "No se pudo guardar el filtro", mensaje: String(e), tipo: "error" });
    }
  };

  const onAplicarPresetClick = (preset: FiltroGuardado) => {
    setFilas(rangosIniciales(campos, rangosDeFiltroAStrings(preset.rangos)));
    onAplicarPreset(preset.busqueda, rangosDeFiltroAStrings(preset.rangos));
    onCerrar();
  };

  const onEliminarPreset = async (nombre: string) => {
    try {
      setPresets(await api.eliminarFiltro(machineId, nombre));
    } catch (e) {
      await avisar({ titulo: "No se pudo eliminar el filtro", mensaje: String(e), tipo: "error" });
    }
  };

  return (
    <Modal
      titulo="Filtros avanzados"
      ancho={480}
      onCerrar={onCerrar}
      ayuda="Rango numérico (dejá vacío el que no quieras limitar):"
      footer={
        <>
          <span className="ui-modal__footer-sep" />
          <Boton tipo="secondary" onClick={onCerrar}>
            Cerrar
          </Boton>
          <Boton tipo="primary" onClick={onAceptarAplicar}>
            Aplicar
          </Boton>
        </>
      }
    >
      {error && <p className="error">{error}</p>}

      <div className="flt-tabla">
        {campos.map((c) => {
          const extremos = filas[c.nombre_interno] ?? { min: "", max: "" };
          return (
            <div className="flt-fila" key={c.nombre_interno}>
              <span className="flt-titulo">{c.titulo_ui}</span>
              <input
                className="flt-input"
                value={extremos.min}
                inputMode="decimal"
                onChange={(e) =>
                  setFilas((f) => ({
                    ...f,
                    [c.nombre_interno]: { ...extremos, min: e.target.value },
                  }))
                }
              />
              <span className="flt-a">a</span>
              <input
                className="flt-input"
                value={extremos.max}
                inputMode="decimal"
                onChange={(e) =>
                  setFilas((f) => ({
                    ...f,
                    [c.nombre_interno]: { ...extremos, max: e.target.value },
                  }))
                }
              />
            </div>
          );
        })}
      </div>

      <div className="flt-acciones">
        <Boton tipo="outline" chico onClick={onLimpiar}>
          Limpiar filtros
        </Boton>
        <Boton
          tipo="outline"
          chico
          onClick={() => setMostrarGuardar((v) => !v)}
          tooltip="Guardar la búsqueda + estos rangos como un filtro frecuente para reaplicar después"
        >
          Guardar como…
        </Boton>
      </div>

      {mostrarGuardar && (
        <div className="flt-guardar">
          <input
            placeholder="Nombre del filtro"
            value={nombreNuevo}
            autoFocus
            onChange={(e) => setNombreNuevo(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter") {
                e.preventDefault();
                void onGuardarComo();
              }
            }}
          />
          <Boton tipo="primary" chico onClick={() => void onGuardarComo()} disabled={!nombreNuevo.trim()}>
            Guardar
          </Boton>
        </div>
      )}

      <p className="flt-subtitulo">Filtros guardados:</p>
      {!presets ? (
        <p className="muted">Cargando…</p>
      ) : presets.length === 0 ? (
        <p className="muted">(ninguno todavía)</p>
      ) : (
        <div className="flt-presets">
          {presets.map((p) => (
            <div className="flt-preset" key={p.nombre}>
              <span>{p.nombre}</span>
              <Boton tipo="ghost" chico onClick={() => void onEliminarPreset(p.nombre)}>
                Eliminar
              </Boton>
              <Boton tipo="outline" chico onClick={() => onAplicarPresetClick(p)}>
                Aplicar
              </Boton>
            </div>
          ))}
        </div>
      )}
    </Modal>
  );
}
