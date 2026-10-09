import { useState } from "react";
import {
  api,
  type Campo,
  type ImportAplicarResultado,
  type ImportConflicto,
  type ImportDiffRegistro,
  type ImportMapeoResultado,
  type ImportObsoleto,
} from "../api";
import { Boton, Modal, useDialogos } from "../ui";

const SKIP = "";
/** Clave interna para la columna de búsqueda en el mapa de columnas usadas. */
const BUSQUEDA = "__busqueda__";

type Fase = "elegir_archivo" | "hoja" | "mapeo" | "diff";

/**
 * Importar cambios desde un Excel o CSV en dos pasos de mapeo:
 *
 * 1. Clave de búsqueda: un campo del sistema (sin ID) y la columna del
 *    archivo que lo identifica. Cada fila del archivo se busca por este valor.
 * 2. Datos a actualizar: columnas del archivo → parámetros del sistema. Si la
 *    celda del archivo está vacía, el dato actual no se toca.
 *
 * Los códigos del archivo que no están en el sistema solo se avisan: no se
 * crean registros. Los códigos repetidos son conflictos y no se importan.
 * Plan: docs/PLAN_IMPORTACION_CLAVE_BUSQUEDA.md.
 */
export default function ImportarDialog({
  machineId,
  campos,
  hashEsperado,
  onAplicado,
  onCerrar,
}: {
  machineId: string;
  /** Campos visibles del perfil (incluida la clave y el ID automático), en orden. */
  campos: Campo[];
  hashEsperado: string | null;
  onAplicado: (hash: string, resumen: ImportAplicarResultado) => void;
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
  const [busqCampo, setBusqCampo] = useState<string>(SKIP);
  const [busqColumna, setBusqColumna] = useState<string>(SKIP);
  const [mapeo, setMapeo] = useState<Record<string, string>>({});

  const [resultado, setResultado] = useState<ImportMapeoResultado | null>(null);
  const [selDiffs, setSelDiffs] = useState<Set<string>>(new Set());
  const [selObsoletos, setSelObsoletos] = useState<Set<string>>(new Set());

  // Clave de búsqueda: cualquier campo visible, salvo el ID automático.
  const camposBusqueda = campos.filter((c) => !c.sintetica);
  // Datos a actualizar: solo parámetros (nunca la clave ni el ID).
  const camposDatos = campos.filter((c) => c.rol === "parametro" && !c.sintetica);
  const titulo = (nombreInterno: string) =>
    campos.find((c) => c.nombre_interno === nombreInterno)?.titulo_ui ?? nombreInterno;

  /** Columnas ya usadas por OTRA parte del mapeo (la clave o un dato distinto a `parte`). */
  const columnasUsadasSin = (parte: string): Set<string> => {
    const usadas = new Set<string>();
    if (parte !== BUSQUEDA && busqColumna) usadas.add(busqColumna);
    for (const [k, v] of Object.entries(mapeo)) {
      if (k !== parte && v) usadas.add(v);
    }
    return usadas;
  };

  type Sugerencias = {
    sugerencia: Record<string, string | null>;
    sugerencia_busqueda: { campo: string | null; columna: string | null };
  };
  const aplicarSugerencias = (r: Sugerencias) => {
    setBusqCampo(r.sugerencia_busqueda.campo ?? SKIP);
    setBusqColumna(r.sugerencia_busqueda.columna ?? SKIP);
    setMapeo(Object.fromEntries(camposDatos.map((c) => [c.nombre_interno, r.sugerencia[c.nombre_interno] ?? SKIP])));
  };

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
      aplicarSugerencias(r);
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
      aplicarSugerencias(r);
      setFase("mapeo");
    } catch (e) {
      setError(String(e));
    } finally {
      setCargando(false);
    }
  };

  // -- paso 3: clave de búsqueda + datos -------------------------------------
  const puedeContinuarMapeo = busqCampo !== SKIP && busqColumna !== SKIP;

  const onContinuarMapeo = async () => {
    if (!importId) return;
    setCargando(true);
    setError(null);
    const mapeoEnviado = Object.fromEntries(
      Object.entries(mapeo).filter(([k, v]) => v !== SKIP && k !== busqCampo),
    );
    try {
      const r = await api.importMapear(
        machineId,
        importId,
        { campo: busqCampo, columna: busqColumna },
        mapeoEnviado,
      );
      setResultado(r);
      setSelDiffs(new Set());
      setSelObsoletos(new Set());
      setFase("diff");
    } catch (e) {
      setError(String(e));
    } finally {
      setCargando(false);
    }
  };

  // -- paso 4: revisar y aplicar --------------------------------------------------
  const setAll = (items: { id: string; errores?: unknown[] }[], setSel: (v: Set<string>) => void, value: boolean) => {
    setSel(value ? new Set(items.filter((i) => !i.errores?.length).map((i) => i.id)) : new Set());
  };

  const alternarEn = (set: Set<string>, setSel: (v: Set<string>) => void, id: string) => {
    const n = new Set(set);
    if (n.has(id)) n.delete(id);
    else n.add(id);
    setSel(n);
  };

  const onAplicar = async () => {
    if (!importId) return;
    const total = selDiffs.size + selObsoletos.size;
    if (total === 0) {
      await avisar({ titulo: "Sin selección", mensaje: "No marcaste ningún cambio para aplicar." });
      return;
    }
    const partes: string[] = [];
    if (selDiffs.size) partes.push(`${selDiffs.size} modificación(es)`);
    if (selObsoletos.size) partes.push(`${selObsoletos.size} registro(s) a eliminar`);
    const ids = [...selDiffs, ...selObsoletos];
    const preview6 = ids.slice(0, 6).join(", ") + (ids.length > 6 ? " …" : "");
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
      const r = await api.importAplicar(machineId, importId, [...selDiffs], [...selObsoletos], hashEsperado);
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
          <p style={{ fontWeight: 600, marginBottom: "0.25rem" }}>1. Clave de búsqueda</p>
          <p className="muted">
            Código que identifica cada registro (número o sellado). Cada fila del archivo se
            busca por este valor. Es obligatoria.
          </p>
          <div className="imp-mapeo">
            <div className="imp-mapeo-fila">
              <span className="imp-mapeo-titulo">Campo del sistema</span>
              <select
                value={busqCampo}
                onChange={(e) => setBusqCampo(e.target.value)}
              >
                <option value={SKIP}>— elegí un campo —</option>
                {camposBusqueda.map((c) => (
                  <option key={c.nombre_interno} value={c.nombre_interno}>
                    {c.titulo_ui}
                  </option>
                ))}
              </select>
            </div>
            <div className="imp-mapeo-fila">
              <span className="imp-mapeo-titulo">Columna del archivo</span>
              <select
                value={busqColumna}
                onChange={(e) => setBusqColumna(e.target.value)}
              >
                <option value={SKIP}>— elegí una columna —</option>
                {headers.map((h) => (
                  <option key={h} value={h} disabled={columnasUsadasSin(BUSQUEDA).has(h)}>
                    {h}
                  </option>
                ))}
              </select>
            </div>
          </div>

          <p style={{ fontWeight: 600, margin: "1.25rem 0 0.25rem" }}>2. Datos a actualizar</p>
          <p className="muted">
            Indicá qué columna del archivo corresponde a cada dato. Si la celda del archivo está
            vacía, el dato actual no se toca. Dejá «no importar» en los que el archivo no trae.
          </p>
          <div className="imp-mapeo">
            {camposDatos
              .filter((c) => c.nombre_interno !== busqCampo)
              .map((c) => {
                const usadas = columnasUsadasSin(c.nombre_interno);
                return (
                  <div className="imp-mapeo-fila" key={c.nombre_interno}>
                    <span className="imp-mapeo-titulo">{c.titulo_ui}</span>
                    <select
                      value={mapeo[c.nombre_interno] ?? SKIP}
                      onChange={(e) =>
                        setMapeo((m) => ({ ...m, [c.nombre_interno]: e.target.value }))
                      }
                    >
                      <option value={SKIP}>— no importar —</option>
                      {headers.map((h) => (
                        <option key={h} value={h} disabled={usadas.has(h)}>
                          {h}
                        </option>
                      ))}
                    </select>
                  </div>
                );
              })}
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
            <Boton
              tipo="primary"
              onClick={() => void onContinuarMapeo()}
              disabled={cargando || !puedeContinuarMapeo}
            >
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
            selObsoletos={selObsoletos}
            setSelDiffs={setSelDiffs}
            setSelObsoletos={setSelObsoletos}
            alternarEn={alternarEn}
            setAll={setAll}
            titulo={titulo}
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
  selObsoletos,
  setSelDiffs,
  setSelObsoletos,
  alternarEn,
  setAll,
  titulo,
}: {
  resultado: ImportMapeoResultado;
  selDiffs: Set<string>;
  selObsoletos: Set<string>;
  setSelDiffs: (v: Set<string>) => void;
  setSelObsoletos: (v: Set<string>) => void;
  alternarEn: (set: Set<string>, setSel: (v: Set<string>) => void, id: string) => void;
  setAll: (items: { id: string; errores?: unknown[] }[], setSel: (v: Set<string>) => void, value: boolean) => void;
  titulo: (nombreInterno: string) => string;
}) {
  const { diffs, conflictos, sin_coincidencia, obsoletos, sin_cambios, filas_sin_clave } = resultado;
  const nInvalidos = diffs.filter((d) => d.errores.length).length;

  const partes = [`${diffs.length} con diferencias`];
  if (sin_cambios) partes.push(`${sin_cambios} sin cambios`);
  if (sin_coincidencia.length) partes.push(`${sin_coincidencia.length} sin coincidencia`);
  if (conflictos.length) partes.push(`${conflictos.length} con conflicto`);
  if (obsoletos.length) partes.push(`${obsoletos.length} en el sistema y no en el archivo`);
  if (filas_sin_clave) partes.push(`${filas_sin_clave} fila(s) sin clave`);

  const hayAlgo = diffs.length || conflictos.length || sin_coincidencia.length || obsoletos.length;
  if (!hayAlgo) {
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
            <div key={d.id} className={"imp-card" + (d.errores.length ? " imp-card--invalido" : "")}>
              <label className="imp-card-head">
                <input
                  type="checkbox"
                  checked={selDiffs.has(d.id)}
                  disabled={d.errores.length > 0}
                  onChange={() => alternarEn(selDiffs, setSelDiffs, d.id)}
                />
                <strong>{d.busqueda}</strong>
                {d.id !== d.busqueda && <span className="muted">(ID {d.id})</span>}
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

      {conflictos.length > 0 && (
        <section className="imp-seccion">
          <div className="imp-seccion-header">
            <span style={{ color: "var(--danger)", fontWeight: 600 }}>Conflictos (no se importan)</span>
          </div>
          <p className="muted">
            Hay que corregir el dato en el archivo o en el sistema para poder importarlos.
          </p>
          {conflictos.map((c: ImportConflicto) => (
            <div className="imp-card imp-card--invalido" key={c.codigo}>
              <strong>{c.codigo}</strong>
              <p className="error">⚠ {c.motivo}</p>
            </div>
          ))}
        </section>
      )}

      {sin_coincidencia.length > 0 && (
        <section className="imp-seccion">
          <div className="imp-seccion-header">
            <span style={{ color: "var(--warning)", fontWeight: 600 }}>
              Códigos del archivo que no están en el sistema
            </span>
          </div>
          <p className="muted">
            Solo se avisan: no se crean ni se modifican registros. El ingeniero los carga.
          </p>
          <div className="imp-card">
            {sin_coincidencia.map((s) => (
              <div className="imp-card-fila" key={s.codigo}>
                <span>{s.codigo}</span>
              </div>
            ))}
          </div>
        </section>
      )}

      {obsoletos.length > 0 && (
        <section className="imp-seccion">
          <SeccionHeader
            titulo="Registros del sistema que no están en el archivo"
            color="var(--danger)"
            onTodos={() => setAll(obsoletos, setSelObsoletos, true)}
            onNinguno={() => setAll(obsoletos, setSelObsoletos, false)}
          />
          <p className="muted">
            Marcá los que quieras eliminar del catálogo por estar obsoletos. Los que dejes sin
            marcar se conservan tal cual están.
          </p>
          {obsoletos.map((d: ImportObsoleto) => (
            <div className="imp-card" key={d.id}>
              <label className="imp-card-head">
                <input
                  type="checkbox"
                  checked={selObsoletos.has(d.id)}
                  onChange={() => alternarEn(selObsoletos, setSelObsoletos, d.id)}
                />
                {d.busqueda}
                {d.id !== d.busqueda && <span className="muted">(ID {d.id})</span>}
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
