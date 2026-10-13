import { useState } from "react";
import {
  api,
  type Campo,
  type ImportAlta,
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
/** Prefijo para las claves de la carga masiva (`__clave0__`, `__clave1__`). */
const CLAVE = "__clave__";

type Fase = "modo" | "elegir_archivo" | "hoja" | "mapeo" | "diff";
type Modo = "carga" | "actualizacion";
type Clave = { campo: string; columna: string };

/**
 * Importar datos desde un Excel o CSV. Dos modos:
 *
 * - Actualización masiva: cambia registros que ya existen. Cada fila se busca
 *   por una clave (un campo del sistema) y las celdas vacías no tocan el dato
 *   actual. Los códigos que no están en el sistema solo se avisan.
 * - Carga masiva: crea un registro por fila con ID automático. Hasta dos
 *   campos forman la clave (p. ej. amortiguador y número de sellado): si ya
 *   existe un registro con esas claves se modifica; si no, se da de alta. Las
 *   celdas vacías quedan en 0 (numérico) o Null (texto).
 *
 * Los códigos repetidos son conflictos y no se importan.
 * Planes: docs/PLAN_IMPORTACION_CLAVE_BUSQUEDA.md y docs/PLAN_CARGA_MASIVA.md.
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
  const [fase, setFase] = useState<Fase>("modo");
  const [modo, setModo] = useState<Modo>("actualizacion");
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
  // Carga masiva: hasta dos claves (la segunda es opcional).
  const [claves, setClaves] = useState<Clave[]>([
    { campo: SKIP, columna: SKIP },
    { campo: SKIP, columna: SKIP },
  ]);
  const [mapeo, setMapeo] = useState<Record<string, string>>({});

  const [resultado, setResultado] = useState<ImportMapeoResultado | null>(null);
  const [selDiffs, setSelDiffs] = useState<Set<string>>(new Set());
  const [selObsoletos, setSelObsoletos] = useState<Set<string>>(new Set());
  const [selAltas, setSelAltas] = useState<Set<string>>(new Set());

  // Clave de búsqueda: cualquier campo visible, salvo el ID automático.
  const camposBusqueda = campos.filter((c) => !c.sintetica);
  // Datos a actualizar (actualización): solo parámetros, nunca la clave ni el ID.
  const camposDatos = campos.filter((c) => c.rol === "parametro" && !c.sintetica);
  // Campos que se eligen como clave en la carga, y los que el archivo puede traer.
  const clavesCampos = modo === "carga"
    ? claves.map((k) => k.campo).filter((c) => c !== SKIP)
    : [busqCampo];
  const camposDatosModo = modo === "carga"
    ? camposBusqueda.filter((c) => !clavesCampos.includes(c.nombre_interno))
    : camposDatos.filter((c) => c.nombre_interno !== busqCampo);
  const titulo = (nombreInterno: string) =>
    campos.find((c) => c.nombre_interno === nombreInterno)?.titulo_ui ?? nombreInterno;

  /** Columnas ya usadas por OTRA parte del mapeo (una clave o un dato distinto a `parte`). */
  const columnasUsadasSin = (parte: string): Set<string> => {
    const usadas = new Set<string>();
    if (modo === "carga") {
      claves.forEach((k, i) => {
        if (`${CLAVE}${i}` !== parte && k.columna) usadas.add(k.columna);
      });
    } else if (parte !== BUSQUEDA && busqColumna) {
      usadas.add(busqColumna);
    }
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
    // La carga arranca vacía: las claves las elige el operario.
    if (modo === "carga") return;
    setBusqCampo(r.sugerencia_busqueda.campo ?? SKIP);
    setBusqColumna(r.sugerencia_busqueda.columna ?? SKIP);
    setMapeo(Object.fromEntries(camposDatos.map((c) => [c.nombre_interno, r.sugerencia[c.nombre_interno] ?? SKIP])));
  };

  const setClave = (i: number, parte: "campo" | "columna", valor: string) =>
    setClaves((cs) => cs.map((k, j) => (j === i ? { ...k, [parte]: valor } : k)));

  // -- paso 0: elegir modo ----------------------------------------------------
  const elegirModo = (m: Modo) => {
    setModo(m);
    setError(null);
    setFase("elegir_archivo");
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
  const claveCompleta = (k: Clave) => k.campo !== SKIP && k.columna !== SKIP;
  const claveVacia = (k: Clave) => k.campo === SKIP && k.columna === SKIP;
  const puedeContinuarMapeo = modo === "carga"
    ? claveCompleta(claves[0]) &&
      (claveVacia(claves[1]) || (claveCompleta(claves[1]) && claves[1].campo !== claves[0].campo))
    : busqCampo !== SKIP && busqColumna !== SKIP;

  const onContinuarMapeo = async () => {
    if (!importId) return;
    setCargando(true);
    setError(null);
    try {
      let r: ImportMapeoResultado;
      if (modo === "carga") {
        const clavesEnviadas = claves
          .filter(claveCompleta)
          .map((k) => ({ campo: k.campo, columna: k.columna }));
        const mapeoCarga = Object.fromEntries(
          Object.entries(mapeo).filter(([k, v]) => v !== SKIP && !clavesCampos.includes(k)),
        );
        r = await api.importMapearCarga(machineId, importId, clavesEnviadas, mapeoCarga);
      } else {
        const mapeoEnviado = Object.fromEntries(
          Object.entries(mapeo).filter(([k, v]) => v !== SKIP && k !== busqCampo),
        );
        r = await api.importMapear(
          machineId,
          importId,
          { campo: busqCampo, columna: busqColumna },
          mapeoEnviado,
        );
      }
      setResultado(r);
      setSelDiffs(new Set());
      setSelObsoletos(new Set());
      setSelAltas(new Set());
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
    const total = selDiffs.size + selObsoletos.size + selAltas.size;
    if (total === 0) {
      await avisar({ titulo: "Sin selección", mensaje: "No marcaste ningún cambio para aplicar." });
      return;
    }
    const partes: string[] = [];
    if (selAltas.size) partes.push(`${selAltas.size} registro(s) nuevo(s)`);
    if (selDiffs.size) partes.push(`${selDiffs.size} modificación(es)`);
    if (selObsoletos.size) partes.push(`${selObsoletos.size} registro(s) a eliminar`);
    const ids = [...selAltas, ...selDiffs, ...selObsoletos];
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
      const r = await api.importAplicar(
        machineId,
        importId,
        [...selDiffs],
        [...selObsoletos],
        hashEsperado,
        [...selAltas],
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
    modo: "Importar datos",
    elegir_archivo: modo === "carga" ? "Carga masiva" : "Actualización masiva",
    hoja: "Elegí la hoja del Excel",
    mapeo: "Mapear columnas",
    diff: "Revisar cambios",
  };

  /** Fila de una clave: campo del sistema + columna del archivo. */
  const filaClave = (
    prefijo: string,
    campo: string,
    columna: string,
    setCampo: (v: string) => void,
    setColumna: (v: string) => void,
    usadas: Set<string>,
    opcional = false,
  ) => (
    <>
      <div className="imp-mapeo-fila">
        <span className="imp-mapeo-titulo">{prefijo}Campo del sistema</span>
        <select value={campo} onChange={(e) => setCampo(e.target.value)}>
          <option value={SKIP}>{opcional ? "— sin segunda clave —" : "— elegí un campo —"}</option>
          {camposBusqueda.map((c) => (
            <option key={c.nombre_interno} value={c.nombre_interno}>
              {c.titulo_ui}
            </option>
          ))}
        </select>
      </div>
      <div className="imp-mapeo-fila">
        <span className="imp-mapeo-titulo">{prefijo}Columna del archivo</span>
        <select value={columna} onChange={(e) => setColumna(e.target.value)}>
          <option value={SKIP}>— elegí una columna —</option>
          {headers.map((h) => (
            <option key={h} value={h} disabled={usadas.has(h)}>
              {h}
            </option>
          ))}
        </select>
      </div>
    </>
  );

  return (
    <Modal titulo={titulos[fase]} ancho={720} onCerrar={onCerrar}>
      {error && <p className="error">{error}</p>}

      {fase === "modo" && (
        <div className="imp-paso">
          <p className="muted">¿Qué querés hacer con el archivo?</p>
          <div style={{ display: "flex", flexDirection: "column", gap: "1rem" }}>
            <div>
              <Boton tipo="primary" onClick={() => elegirModo("carga")}>
                Carga masiva
              </Boton>
              <p className="muted" style={{ marginTop: "0.25rem" }}>
                Crea un registro nuevo por cada fila (con ID automático). Si ya existe un registro
                con las claves elegidas, lo modifica.
              </p>
            </div>
            <div>
              <Boton tipo="secondary" onClick={() => elegirModo("actualizacion")}>
                Actualización masiva
              </Boton>
              <p className="muted" style={{ marginTop: "0.25rem" }}>
                Actualiza los registros que ya existen. No crea registros nuevos.
              </p>
            </div>
          </div>
          <div className="ui-modal__footer" style={{ marginTop: "1.5rem" }}>
            <span className="ui-modal__footer-sep" />
            <Boton tipo="secondary" onClick={onCerrar}>
              Cancelar
            </Boton>
          </div>
        </div>
      )}

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
          {modo === "carga" ? (
            <>
              <p style={{ fontWeight: 600, marginBottom: "0.25rem" }}>1. Claves de búsqueda</p>
              <p className="muted">
                Campos que identifican cada registro (por ejemplo amortiguador y número de sellado).
                Elegí una o dos; la segunda es opcional. Si la fila ya existe en el sistema con esas
                claves, se modifica; si no, se crea un registro nuevo.
              </p>
              <div className="imp-mapeo">
                {filaClave("Clave 1 · ", claves[0].campo, claves[0].columna,
                  (v) => setClave(0, "campo", v), (v) => setClave(0, "columna", v),
                  columnasUsadasSin(`${CLAVE}0`))}
                {filaClave("Clave 2 · ", claves[1].campo, claves[1].columna,
                  (v) => setClave(1, "campo", v), (v) => setClave(1, "columna", v),
                  columnasUsadasSin(`${CLAVE}1`), true)}
              </div>
            </>
          ) : (
            <>
              <p style={{ fontWeight: 600, marginBottom: "0.25rem" }}>1. Clave de búsqueda</p>
              <p className="muted">
                Código que identifica cada registro (número o sellado). Cada fila del archivo se
                busca por este valor. Es obligatoria.
              </p>
              <div className="imp-mapeo">
                {filaClave("", busqCampo, busqColumna, setBusqCampo, setBusqColumna,
                  columnasUsadasSin(BUSQUEDA))}
              </div>
            </>
          )}

          <p style={{ fontWeight: 600, margin: "1.25rem 0 0.25rem" }}>2. Datos</p>
          <p className="muted">
            {modo === "carga"
              ? "Indicá qué columna del archivo corresponde a cada dato del registro. Las celdas vacías quedan en 0 (numéricos) o Null (texto). Dejá «no importar» en los que el archivo no trae."
              : "Indicá qué columna del archivo corresponde a cada dato. Si la celda del archivo está vacía, el dato actual no se toca. Dejá «no importar» en los que el archivo no trae."}
          </p>
          <div className="imp-mapeo">
            {camposDatosModo.map((c) => {
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
            selAltas={selAltas}
            setSelDiffs={setSelDiffs}
            setSelObsoletos={setSelObsoletos}
            setSelAltas={setSelAltas}
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
  selAltas,
  setSelDiffs,
  setSelObsoletos,
  setSelAltas,
  alternarEn,
  setAll,
  titulo,
}: {
  resultado: ImportMapeoResultado;
  selDiffs: Set<string>;
  selObsoletos: Set<string>;
  selAltas: Set<string>;
  setSelDiffs: (v: Set<string>) => void;
  setSelObsoletos: (v: Set<string>) => void;
  setSelAltas: (v: Set<string>) => void;
  alternarEn: (set: Set<string>, setSel: (v: Set<string>) => void, id: string) => void;
  setAll: (items: { id: string; errores?: unknown[] }[], setSel: (v: Set<string>) => void, value: boolean) => void;
  titulo: (nombreInterno: string) => string;
}) {
  const { diffs, altas, conflictos, sin_coincidencia, obsoletos, sin_cambios, filas_sin_clave } = resultado;
  const nInvalidos = diffs.filter((d) => d.errores.length).length + altas.filter((a) => a.errores.length).length;

  const partes: string[] = [];
  if (altas.length) partes.push(`${altas.length} nuevo(s) para crear`);
  partes.push(`${diffs.length} con diferencias`);
  if (sin_cambios) partes.push(`${sin_cambios} sin cambios`);
  if (sin_coincidencia.length) partes.push(`${sin_coincidencia.length} sin coincidencia`);
  if (conflictos.length) partes.push(`${conflictos.length} con conflicto`);
  if (obsoletos.length) partes.push(`${obsoletos.length} en el sistema y no en el archivo`);
  if (filas_sin_clave) partes.push(`${filas_sin_clave} fila(s) sin clave`);

  const hayAlgo = altas.length || diffs.length || conflictos.length || sin_coincidencia.length || obsoletos.length;
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

      {altas.length > 0 && (
        <section className="imp-seccion">
          <SeccionHeader
            titulo="Registros nuevos (se crean)"
            color="var(--primary-dark)"
            onTodos={() => setAll(altas, setSelAltas, true)}
            onNinguno={() => setAll(altas, setSelAltas, false)}
          />
          {altas.map((a: ImportAlta) => (
            <div key={a.id} className={"imp-card" + (a.errores.length ? " imp-card--invalido" : "")}>
              <label className="imp-card-head">
                <input
                  type="checkbox"
                  checked={selAltas.has(a.id)}
                  disabled={a.errores.length > 0}
                  onChange={() => alternarEn(selAltas, setSelAltas, a.id)}
                />
                <strong>{a.busqueda}</strong>
              </label>
              {Object.entries(a.new).map(([campo, valor]) => (
                <div className="imp-card-fila" key={campo}>
                  <span className="imp-card-campo">{titulo(campo)}</span>
                  <span>{valor == null ? "Null (vacío)" : String(valor)}</span>
                </div>
              ))}
              {a.errores.map((err, i) => (
                <p className="error" key={i}>
                  ⚠ {err.mensaje}
                </p>
              ))}
            </div>
          ))}
        </section>
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
