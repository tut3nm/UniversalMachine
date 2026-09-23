import { useState } from "react";
import {
  api,
  type Campo,
  type ImportDiffRegistro,
  type ImportMapeoResultado,
  type ImportNuevoRegistro,
  type ImportObsoleto,
} from "../api";
import { Boton, Modal, useDialogos } from "../ui";

const SKIP = "";

type Fase = "elegir_archivo" | "hoja" | "mapeo" | "diff";

/**
 * Importar cambios desde un Excel o CSV: elegir hoja (solo si hay más de
 * una), mapear columnas a campos del perfil, y revisar/aplicar las
 * diferencias. Copia `ImportDialog` del escritorio: el mapeo recordado
 * de la última
 * importación tiene prioridad sobre la sugerencia automática, la vista
 * previa muestra las primeras filas crudas, y el paso de diferencias
 * agrupa en tres secciones con "Todos"/"Ninguno" que no marca los ítems
 * con error de validación.
 */
export default function ImportarDialog({
  machineId,
  campos,
  hashEsperado,
  onAplicado,
  onCerrar,
}: {
  machineId: string;
  /** Campos visibles del perfil (incluida la clave), en orden. */
  campos: Campo[];
  hashEsperado: string | null;
  onAplicado: (hash: string, resumen: { modificados: number; nuevos: number; eliminados: number }) => void;
  onCerrar: () => void;
}) {
  const { avisar, confirmar } = useDialogos();
  const [fase, setFase] = useState<Fase>("elegir_archivo");
  const [archivo, setArchivo] = useState<File | null>(null);
  const [cargando, setCargando] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const [importId, setImportId] = useState<string | null>(null);
  const [hojas, setHojas] = useState<string[]>([]);
  const [hojaElegida, setHojaElegida] = useState<string>("");
  const [headers, setHeaders] = useState<string[]>([]);
  const [preview, setPreview] = useState<unknown[][]>([]);
  const [mapeo, setMapeo] = useState<Record<string, string>>({});

  const [resultado, setResultado] = useState<ImportMapeoResultado | null>(null);
  const [selDiffs, setSelDiffs] = useState<Set<string>>(new Set());
  const [selNuevos, setSelNuevos] = useState<Set<string>>(new Set());
  const [selObsoletos, setSelObsoletos] = useState<Set<string>>(new Set());

  // -- paso 1: elegir archivo --------------------------------------------------
  const onContinuarArchivo = async () => {
    if (!archivo) return;
    setCargando(true);
    setError(null);
    try {
      const r = await api.importIniciar(machineId, archivo);
      setImportId(r.import_id);
      setHojas(r.hojas);
      setHojaElegida(r.hoja);
      setHeaders(r.headers);
      setPreview(r.preview);
      setMapeo(Object.fromEntries(campos.map((c) => [c.nombre_interno, r.sugerencia[c.nombre_interno] ?? SKIP])));
      setFase(r.hojas.length > 1 ? "hoja" : "mapeo");
    } catch (e) {
      setError(String(e));
    } finally {
      setCargando(false);
    }
  };

  // -- paso 2: elegir hoja (solo si hay varias) --------------------------------
  const onContinuarHoja = async () => {
    if (!importId) return;
    setCargando(true);
    setError(null);
    try {
      const r = await api.importElegirHoja(machineId, importId, hojaElegida);
      setHeaders(r.headers);
      setPreview(r.preview);
      setMapeo(Object.fromEntries(campos.map((c) => [c.nombre_interno, r.sugerencia[c.nombre_interno] ?? SKIP])));
      setFase("mapeo");
    } catch (e) {
      setError(String(e));
    } finally {
      setCargando(false);
    }
  };

  // -- paso 3: mapear columnas --------------------------------------------------
  const onContinuarMapeo = async () => {
    if (!importId) return;
    setCargando(true);
    setError(null);
    const mapeoEnviado = Object.fromEntries(
      Object.entries(mapeo).filter(([, v]) => v !== SKIP),
    );
    try {
      const r = await api.importMapear(machineId, importId, mapeoEnviado);
      setResultado(r);
      setSelDiffs(new Set());
      setSelNuevos(new Set());
      setSelObsoletos(new Set());
      setFase("diff");
    } catch (e) {
      setError(String(e));
    } finally {
      setCargando(false);
    }
  };

  // -- paso 4: revisar y aplicar --------------------------------------------------
  const setAll = (
    items: { code: string; errores?: unknown[] }[],
    setSel: (v: Set<string>) => void,
    value: boolean,
  ) => {
    setSel(
      value
        ? new Set(items.filter((i) => !i.errores?.length).map((i) => i.code))
        : new Set(),
    );
  };

  const alternarEn = (set: Set<string>, setSel: (v: Set<string>) => void, code: string) => {
    const n = new Set(set);
    if (n.has(code)) n.delete(code);
    else n.add(code);
    setSel(n);
  };

  const onAplicar = async () => {
    if (!importId) return;
    const total = selDiffs.size + selNuevos.size + selObsoletos.size;
    if (total === 0) {
      await avisar({ titulo: "Sin selección", mensaje: "No marcaste ningún cambio para aplicar." });
      return;
    }
    const partes: string[] = [];
    if (selDiffs.size) partes.push(`${selDiffs.size} modificación(es)`);
    if (selNuevos.size) partes.push(`${selNuevos.size} código(s) nuevo(s)`);
    if (selObsoletos.size) partes.push(`${selObsoletos.size} código(s) a eliminar`);
    const codigos = [...selDiffs, ...selNuevos, ...selObsoletos];
    const preview6 = codigos.slice(0, 6).join(", ") + (codigos.length > 6 ? " …" : "");
    let mensaje = `¿Aplicar ${partes.join(", ")}?`;
    if (selObsoletos.size)
      mensaje += `\n\n¡Atención! Esto borra permanentemente ${selObsoletos.size} registro(s) del catálogo.`;
    mensaje += `\n\n${preview6}`;
    const ok = await confirmar({
      titulo: "Confirmar importación",
      mensaje,
      peligro: selObsoletos.size > 0,
      textoOk: "Aplicar",
      textoCancelar: "Cancelar",
    });
    if (!ok) return;

    setCargando(true);
    setError(null);
    try {
      const r = await api.importAplicar(
        machineId,
        importId,
        [...selDiffs],
        [...selNuevos],
        [...selObsoletos],
        hashEsperado,
      );
      onAplicado(r.hash, r);
      onCerrar();
    } catch (e) {
      setError(String(e));
    } finally {
      setCargando(false);
    }
  };

  // -- render ---------------------------------------------------------------
  const titulos: Record<Fase, string> = {
    elegir_archivo: "Importar cambios",
    hoja: "Elegí la hoja del Excel",
    mapeo: "Mapear columnas",
    diff: "Revisar cambios",
  };

  return (
    <Modal titulo={titulos[fase]} ancho={720} onCerrar={onCerrar}>
      {error && <p className="error">{error}</p>}

      {fase === "elegir_archivo" && (
        <div className="imp-paso">
          <p className="muted">Elegí un archivo .csv, .xlsx o .xlsm con los cambios a importar.</p>
          <input
            type="file"
            accept=".csv,.xlsx,.xlsm"
            onChange={(e) => setArchivo(e.target.files?.[0] ?? null)}
          />
          <div className="ui-modal__footer" style={{ marginTop: "1.5rem" }}>
            <span className="ui-modal__footer-sep" />
            <Boton tipo="secondary" onClick={onCerrar} disabled={cargando}>
              Cancelar
            </Boton>
            <Boton tipo="primary" onClick={() => void onContinuarArchivo()} disabled={!archivo || cargando}>
              {cargando ? "Cargando…" : "Continuar"}
            </Boton>
          </div>
        </div>
      )}

      {fase === "hoja" && (
        <div className="imp-paso">
          <p className="muted">El archivo tiene varias hojas. Elegí la de los datos.</p>
          {hojas.map((h) => (
            <label className="imp-radio" key={h}>
              <input
                type="radio"
                name="hoja"
                checked={hojaElegida === h}
                onChange={() => setHojaElegida(h)}
              />
              {h}
            </label>
          ))}
          <div className="ui-modal__footer" style={{ marginTop: "1.5rem" }}>
            <span className="ui-modal__footer-sep" />
            <Boton tipo="secondary" onClick={onCerrar} disabled={cargando}>
              Cancelar
            </Boton>
            <Boton tipo="primary" onClick={() => void onContinuarHoja()} disabled={cargando}>
              {cargando ? "Cargando…" : "Continuar"}
            </Boton>
          </div>
        </div>
      )}

      {fase === "mapeo" && (
        <div className="imp-paso">
          <p className="muted">
            Indicá qué columna del archivo corresponde a cada dato. El código es
            obligatorio; el resto es opcional — dejá "no importar" en los datos que
            ese archivo no trae, y no se van a tocar.
          </p>
          <div className="imp-mapeo">
            {campos.map((c) => (
              <div className="imp-mapeo-fila" key={c.nombre_interno}>
                <span className="imp-mapeo-titulo">
                  {c.titulo_ui}
                  {c.rol === "clave" && "  (obligatorio)"}
                </span>
                <select
                  value={mapeo[c.nombre_interno] ?? SKIP}
                  onChange={(e) =>
                    setMapeo((m) => ({ ...m, [c.nombre_interno]: e.target.value }))
                  }
                >
                  <option value={SKIP}>— no importar —</option>
                  {headers.map((h) => (
                    <option key={h} value={h}>
                      {h}
                    </option>
                  ))}
                </select>
              </div>
            ))}
          </div>

          {preview.length > 0 && (
            <>
              <p className="muted" style={{ marginTop: "1rem" }}>
                Vista previa (primeras {preview.length} fila(s) del archivo):
              </p>
              <div className="table-wrap">
                <table>
                  <thead>
                    <tr>
                      {headers.map((h) => (
                        <th key={h}>{h}</th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {preview.map((fila, i) => (
                      <tr key={i}>
                        {headers.map((_, ci) => (
                          <td key={ci}>{String(fila[ci] ?? "")}</td>
                        ))}
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </>
          )}

          <div className="ui-modal__footer" style={{ marginTop: "1.5rem" }}>
            <span className="ui-modal__footer-sep" />
            <Boton tipo="secondary" onClick={onCerrar} disabled={cargando}>
              Cancelar
            </Boton>
            <Boton tipo="primary" onClick={() => void onContinuarMapeo()} disabled={cargando}>
              {cargando ? "Comparando…" : "Continuar"}
            </Boton>
          </div>
        </div>
      )}

      {fase === "diff" && resultado && (
        <div className="imp-paso">
          <SeccionDiffs
            resultado={resultado}
            selDiffs={selDiffs}
            selNuevos={selNuevos}
            selObsoletos={selObsoletos}
            setSelDiffs={setSelDiffs}
            setSelNuevos={setSelNuevos}
            setSelObsoletos={setSelObsoletos}
            alternarEn={alternarEn}
            setAll={setAll}
            campos={campos}
          />
          <div className="ui-modal__footer" style={{ marginTop: "1rem" }}>
            <span className="ui-modal__footer-sep" />
            <Boton tipo="secondary" onClick={onCerrar} disabled={cargando}>
              Cerrar
            </Boton>
            <Boton tipo="primary" onClick={() => void onAplicar()} disabled={cargando}>
              {cargando ? "Aplicando…" : "Aplicar seleccionados"}
            </Boton>
          </div>
        </div>
      )}
    </Modal>
  );
}

function SeccionDiffs({
  resultado,
  selDiffs,
  selNuevos,
  selObsoletos,
  setSelDiffs,
  setSelNuevos,
  setSelObsoletos,
  alternarEn,
  setAll,
  campos,
}: {
  resultado: ImportMapeoResultado;
  selDiffs: Set<string>;
  selNuevos: Set<string>;
  selObsoletos: Set<string>;
  setSelDiffs: (v: Set<string>) => void;
  setSelNuevos: (v: Set<string>) => void;
  setSelObsoletos: (v: Set<string>) => void;
  alternarEn: (set: Set<string>, setSel: (v: Set<string>) => void, code: string) => void;
  setAll: (items: { code: string; errores?: unknown[] }[], setSel: (v: Set<string>) => void, value: boolean) => void;
  campos: Campo[];
}) {
  const titulo = (nombreInterno: string) =>
    campos.find((c) => c.nombre_interno === nombreInterno)?.titulo_ui ?? nombreInterno;

  const { diffs, nuevos, obsoletos, sin_cambios } = resultado;
  const nInvalidos =
    diffs.filter((d) => d.errores.length).length + nuevos.filter((d) => d.errores.length).length;

  const partes = [`${diffs.length} con diferencias`];
  if (sin_cambios) partes.push(`${sin_cambios} sin cambios`);
  if (nuevos.length) partes.push(`${nuevos.length} código(s) nuevo(s)`);
  if (obsoletos.length) partes.push(`${obsoletos.length} código(s) no están en el archivo`);

  if (!diffs.length && !nuevos.length && !obsoletos.length) {
    return <p>No hay cambios para revisar.</p>;
  }

  return (
    <>
      <p className="muted">{partes.join(" · ")}</p>
      {nInvalidos > 0 && (
        <p className="error">
          ⚠ {nInvalidos} valor(es) fuera de rango — no se pueden importar hasta corregir el
          archivo (marcados abajo).
        </p>
      )}

      {diffs.length > 0 && (
        <section className="imp-seccion">
          <SeccionHeader
            titulo="Modificaciones"
            color="var(--primary-dark)"
            onTodos={() => setAll(diffs, setSelDiffs, true)}
            onNinguno={() => setAll(diffs, setSelDiffs, false)}
          />
          {diffs.map((d: ImportDiffRegistro) => (
            <div
              key={d.code}
              className={"imp-card" + (d.errores.length ? " imp-card--invalido" : "")}
            >
              <label className="imp-card-head">
                <input
                  type="checkbox"
                  checked={selDiffs.has(d.code)}
                  disabled={d.errores.length > 0}
                  onChange={() => alternarEn(selDiffs, setSelDiffs, d.code)}
                />
                <strong>{d.code}</strong>
              </label>
              {Object.keys(d.new).map((campo) => {
                const antes = d.old[campo];
                const despues = d.new[campo];
                const redondeado = d.redondeos.includes(campo);
                let texto: string;
                if (despues == null) texto = `${antes}  (sin dato en el archivo, no se modifica)`;
                else if (despues !== antes) texto = `${antes}  →  ${despues}`;
                else texto = `${antes}`;
                if (redondeado) texto += "  ⚠ redondeado (el archivo traía decimales)";
                return (
                  <div className="imp-card-fila" key={campo}>
                    <span className="imp-card-campo">{titulo(campo)}</span>
                    <span className={redondeado ? "diff-modificacion" : ""}>{texto}</span>
                  </div>
                );
              })}
              {d.errores.map((err, i) => (
                <p className="error" key={i}>
                  ⚠ {err.mensaje}
                </p>
              ))}
            </div>
          ))}
        </section>
      )}

      {nuevos.length > 0 && (
        <section className="imp-seccion">
          <SeccionHeader
            titulo="Códigos nuevos para agregar"
            color="var(--warning)"
            onTodos={() => setAll(nuevos, setSelNuevos, true)}
            onNinguno={() => setAll(nuevos, setSelNuevos, false)}
          />
          {nuevos.map((d: ImportNuevoRegistro) => (
            <div
              key={d.code}
              className={"imp-card" + (d.errores.length ? " imp-card--invalido" : "")}
            >
              <label className="imp-card-head">
                <input
                  type="checkbox"
                  checked={selNuevos.has(d.code)}
                  disabled={d.errores.length > 0}
                  onChange={() => alternarEn(selNuevos, setSelNuevos, d.code)}
                />
                <strong>{d.code}</strong>
              </label>
              {Object.entries(d.valores)
                .filter(([campo]) => campos.find((c) => c.nombre_interno === campo)?.rol !== "clave")
                .map(([campo, val]) => (
                  <div className="imp-card-fila" key={campo}>
                    <span className="imp-card-campo">{titulo(campo)}</span>
                    <span>
                      {val == null ? "(sin dato)" : String(val)}
                      {d.redondeos.includes(campo) && "  ⚠ redondeado (el archivo traía decimales)"}
                    </span>
                  </div>
                ))}
              {d.errores.map((err, i) => (
                <p className="error" key={i}>
                  ⚠ {err.mensaje}
                </p>
              ))}
            </div>
          ))}
        </section>
      )}

      {obsoletos.length > 0 && (
        <section className="imp-seccion">
          <SeccionHeader
            titulo="Códigos del catálogo que no están en el archivo"
            color="var(--danger)"
            onTodos={() => setAll(obsoletos, setSelObsoletos, true)}
            onNinguno={() => setAll(obsoletos, setSelObsoletos, false)}
          />
          <p className="muted">
            Marcá los que quieras eliminar del catálogo por estar obsoletos. Los que dejes sin
            marcar se conservan tal cual están.
          </p>
          {obsoletos.map((d: ImportObsoleto) => (
            <div className="imp-card" key={d.code}>
              <label className="imp-card-head">
                <input
                  type="checkbox"
                  checked={selObsoletos.has(d.code)}
                  onChange={() => alternarEn(selObsoletos, setSelObsoletos, d.code)}
                />
                {d.code}
              </label>
            </div>
          ))}
        </section>
      )}
    </>
  );
}

function SeccionHeader({
  titulo,
  color,
  onTodos,
  onNinguno,
}: {
  titulo: string;
  color: string;
  onTodos: () => void;
  onNinguno: () => void;
}) {
  return (
    <div className="imp-seccion-header">
      <span style={{ color, fontWeight: 600 }}>{titulo}</span>
      <Boton tipo="ghost" chico onClick={onTodos}>
        Todos
      </Boton>
      <Boton tipo="ghost" chico onClick={onNinguno}>
        Ninguno
      </Boton>
    </div>
  );
}
