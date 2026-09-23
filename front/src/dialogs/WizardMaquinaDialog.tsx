import { useState } from "react";
import {
  api,
  type FilaClasificada,
  type FilaWizardIn,
  type WizardClasificacion,
  type WizardInicio,
  type WizardValidacion,
} from "../api";
import { Boton, Modal } from "../ui";

type Fase = "archivo" | "orientacion" | "campos" | "validar";

const TIPOS: { valor: string; etiqueta: string }[] = [
  { valor: "texto", etiqueta: "Texto" },
  { valor: "entero", etiqueta: "Entero" },
  { valor: "entero_ceros", etiqueta: "Entero con ceros a la izquierda" },
  { valor: "decimal", etiqueta: "Decimal" },
];

interface FilaEstado {
  nombre: string;
  titulo: string;
  tipo: string;
  incluir: boolean;
  min: string;
  max: string;
  default: string;
}

/**
 * Wizard de alta de máquina nueva: archivo -> orientación -> campos ->
 * validación byte-perfecta -> confirmar. Copia `WizardMachineDialog` del
 * escritorio sobre los endpoints
 * `/api/wizard/*` que ya existían del trabajo del wizard de escritorio —
 * acá solo faltaba la interfaz web. Cualquier fila/columna que no se elija
 * como campo visible queda OCULTA (viaja con cada registro, nunca se
 * muestra ni se edita) — es lo que garantiza el invariante 1 del plan
 * (round-trip byte-perfecto).
 */
export default function WizardMaquinaDialog({
  onCreada,
  onCerrar,
}: {
  onCreada: (machineId: string) => void;
  onCerrar: () => void;
}) {
  const [fase, setFase] = useState<Fase>("archivo");
  const [cargando, setCargando] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const [machineId, setMachineId] = useState("");
  const [nombre, setNombre] = useState("");
  const [descripcion, setDescripcion] = useState("");
  const [archivo, setArchivo] = useState<File | null>(null);

  const [inicio, setInicio] = useState<WizardInicio | null>(null);
  const [orientacion, setOrientacion] = useState<"columnas" | "filas">("columnas");
  const [primeraCol, setPrimeraCol] = useState(1);

  const [clasificacion, setClasificacion] = useState<WizardClasificacion | null>(null);
  const [claveIdx, setClaveIdx] = useState<number | null>(null);
  const [filasEstado, setFilasEstado] = useState<Record<number, FilaEstado>>({});

  const [validacion, setValidacion] = useState<WizardValidacion | null>(null);

  // -- paso 1: archivo e identidad ----------------------------------------------
  const onContinuarArchivo = async () => {
    if (!archivo || !machineId.trim() || !nombre.trim()) return;
    setCargando(true);
    setError(null);
    try {
      const r = await api.wizardIniciarAlta(archivo);
      setInicio(r);
      setFase("orientacion");
    } catch (e) {
      setError(String(e));
    } finally {
      setCargando(false);
    }
  };

  // -- paso 2: orientación --------------------------------------------------------
  const onContinuarOrientacion = async () => {
    if (!inicio) return;
    setCargando(true);
    setError(null);
    try {
      const r = await api.wizardClasificar(inicio.wizard_id, orientacion, primeraCol);
      setClasificacion(r);
      setClaveIdx(r.clave_sugerida);
      const estado: Record<number, FilaEstado> = {};
      for (const f of r.filas) {
        estado[f.idx] = {
          nombre: f.nombre_default,
          titulo: f.titulo_default,
          tipo: f.tipo_sugerido,
          incluir: f.incluir_default,
          min: "",
          max: "",
          default: "",
        };
      }
      setFilasEstado(estado);
      setFase("campos");
    } catch (e) {
      setError(String(e));
    } finally {
      setCargando(false);
    }
  };

  // -- paso 3: campos --------------------------------------------------------------
  const actualizarFila = (idx: number, cambios: Partial<FilaEstado>) =>
    setFilasEstado((s) => ({ ...s, [idx]: { ...s[idx], ...cambios } }));

  const onContinuarCampos = async () => {
    if (!inicio || claveIdx === null) return;
    setCargando(true);
    setError(null);
    try {
      const filas: FilaWizardIn[] = Object.entries(filasEstado).map(([idxTexto, f]) => {
        const idx = Number(idxTexto);
        const esNumerico = f.tipo === "entero" || f.tipo === "entero_ceros" || f.tipo === "decimal";
        return {
          idx,
          incluir: idx === claveIdx ? false : f.incluir,
          nombre: f.nombre,
          titulo: f.titulo,
          etiqueta: f.titulo,
          tipo: f.tipo,
          min: esNumerico && f.min.trim() ? Number(f.min) : null,
          max: esNumerico && f.max.trim() ? Number(f.max) : null,
          default: f.default.trim() || null,
        };
      });
      await api.wizardBuildProfile(
        inicio.wizard_id,
        machineId.trim(),
        nombre.trim(),
        descripcion.trim(),
        claveIdx,
        filas,
      );
      setFase("validar");
      await validar(inicio.wizard_id);
    } catch (e) {
      setError(String(e));
    } finally {
      setCargando(false);
    }
  };

  // -- paso 4: validar y confirmar --------------------------------------------------
  const validar = async (wizardId: string) => {
    setCargando(true);
    setError(null);
    try {
      const r = await api.wizardValidar(wizardId);
      setValidacion(r);
    } catch (e) {
      setError(String(e));
    } finally {
      setCargando(false);
    }
  };

  const onConfirmar = async () => {
    if (!inicio) return;
    setCargando(true);
    setError(null);
    try {
      const r = await api.wizardConfirmar(inicio.wizard_id);
      onCreada(r.machine_id);
    } catch (e) {
      setError(String(e));
    } finally {
      setCargando(false);
    }
  };

  const titulos: Record<Fase, string> = {
    archivo: "Paso 1 de 4 — Máquina y archivo de muestra",
    orientacion: "Paso 2 de 4 — Orientación de los datos",
    campos: "Paso 3 de 4 — Describir los campos",
    validar: "Paso 4 de 4 — Validación y confirmación",
  };

  return (
    <Modal titulo={titulos[fase]} ancho={760} onCerrar={onCerrar}>
      {error && <p className="error">{error}</p>}

      {fase === "archivo" && (
        <div className="wiz-paso">
          <div className="wiz-campo">
            <label htmlFor="wiz-id">Identificador de la máquina</label>
            <input
              id="wiz-id"
              value={machineId}
              onChange={(e) => setMachineId(e.target.value)}
              placeholder="p. ej. 340"
            />
          </div>
          <div className="wiz-campo">
            <label htmlFor="wiz-nombre">Nombre</label>
            <input
              id="wiz-nombre"
              value={nombre}
              onChange={(e) => setNombre(e.target.value)}
              placeholder="p. ej. Máquina 340 — Recetas"
            />
          </div>
          <div className="wiz-campo">
            <label htmlFor="wiz-desc">Descripción (opcional)</label>
            <input
              id="wiz-desc"
              value={descripcion}
              onChange={(e) => setDescripcion(e.target.value)}
            />
          </div>
          <div className="wiz-campo">
            <label>Archivo CSV de muestra</label>
            <input
              type="file"
              accept=".csv"
              onChange={(e) => setArchivo(e.target.files?.[0] ?? null)}
            />
          </div>
          <div className="ui-modal__footer">
            <span className="ui-modal__footer-sep" />
            <Boton tipo="secondary" onClick={onCerrar} disabled={cargando}>
              Cancelar
            </Boton>
            <Boton
              tipo="primary"
              onClick={() => void onContinuarArchivo()}
              disabled={cargando || !archivo || !machineId.trim() || !nombre.trim()}
            >
              {cargando ? "Cargando…" : "Continuar"}
            </Boton>
          </div>
        </div>
      )}

      {fase === "orientacion" && inicio && (
        <div className="wiz-paso">
          <p className="muted">
            El archivo tiene {inicio.n_filas} fila(s) y {inicio.n_columnas} columna(s). Elegí
            cómo están organizados los datos.
          </p>
          <label className="imp-radio">
            <input
              type="radio"
              checked={orientacion === "columnas"}
              onChange={() => setOrientacion("columnas")}
            />
            Cada fila es un campo (código, parámetro 1, parámetro 2…) y cada columna un registro
          </label>
          <label className="imp-radio">
            <input
              type="radio"
              checked={orientacion === "filas"}
              onChange={() => setOrientacion("filas")}
            />
            Cada columna es un campo y cada fila un registro (como una planilla normal)
          </label>
          {orientacion === "columnas" && (
            <div className="wiz-campo">
              <label htmlFor="wiz-primera-col">Primera columna de datos (0 = la primera)</label>
              <input
                id="wiz-primera-col"
                type="number"
                min={0}
                value={primeraCol}
                onChange={(e) => setPrimeraCol(Number(e.target.value))}
                style={{ width: "6rem" }}
              />
            </div>
          )}
          <div className="ui-modal__footer">
            <Boton tipo="ghost" onClick={() => setFase("archivo")} disabled={cargando}>
              Atrás
            </Boton>
            <span className="ui-modal__footer-sep" />
            <Boton tipo="secondary" onClick={onCerrar} disabled={cargando}>
              Cancelar
            </Boton>
            <Boton tipo="primary" onClick={() => void onContinuarOrientacion()} disabled={cargando}>
              {cargando ? "Analizando…" : "Continuar"}
            </Boton>
          </div>
        </div>
      )}

      {fase === "campos" && clasificacion && (
        <div className="wiz-paso">
          <p className="muted">
            Elegí cuál es el código (clave) y qué otras filas/columnas mostrar como parámetros.
            Lo que no marques queda oculto: viaja con cada registro pero nunca se muestra.
          </p>
          <div>
            {clasificacion.filas.map((f: FilaClasificada) => {
              const estado = filasEstado[f.idx];
              if (!estado) return null;
              const esClave = claveIdx === f.idx;
              const esNumerico =
                estado.tipo === "entero" || estado.tipo === "entero_ceros" || estado.tipo === "decimal";
              return (
                <div className="wiz-fila" key={f.idx}>
                  <label>
                    <input
                      type="radio"
                      name="wiz-clave"
                      checked={esClave}
                      onChange={() => setClaveIdx(f.idx)}
                      title="Es la clave (código)"
                    />
                  </label>
                  {esClave ? (
                    <strong>{f.etiqueta || `#${f.idx}`} (código)</strong>
                  ) : (
                    <label style={{ display: "flex", alignItems: "center", gap: "0.4rem" }}>
                      <input
                        type="checkbox"
                        checked={estado.incluir}
                        onChange={(e) => actualizarFila(f.idx, { incluir: e.target.checked })}
                      />
                      <input
                        value={estado.nombre}
                        onChange={(e) => actualizarFila(f.idx, { nombre: e.target.value })}
                        placeholder="nombre_interno"
                        style={{ width: "8rem" }}
                      />
                      <input
                        value={estado.titulo}
                        onChange={(e) => actualizarFila(f.idx, { titulo: e.target.value })}
                        placeholder="Título visible"
                      />
                    </label>
                  )}
                  {!esClave ? (
                    <select
                      value={estado.tipo}
                      onChange={(e) => actualizarFila(f.idx, { tipo: e.target.value })}
                    >
                      {TIPOS.map((t) => (
                        <option key={t.valor} value={t.valor}>
                          {t.etiqueta}
                        </option>
                      ))}
                    </select>
                  ) : (
                    <span />
                  )}
                  {!esClave && esNumerico ? (
                    <span style={{ display: "flex", gap: "0.3rem" }}>
                      <input
                        value={estado.min}
                        onChange={(e) => actualizarFila(f.idx, { min: e.target.value })}
                        placeholder="min"
                        style={{ width: "3.5rem" }}
                      />
                      <input
                        value={estado.max}
                        onChange={(e) => actualizarFila(f.idx, { max: e.target.value })}
                        placeholder="max"
                        style={{ width: "3.5rem" }}
                      />
                    </span>
                  ) : (
                    <span />
                  )}
                  <span className="wiz-fila-muestra">{f.muestra.join(" · ")}</span>
                </div>
              );
            })}
          </div>
          <div className="ui-modal__footer">
            <Boton tipo="ghost" onClick={() => setFase("orientacion")} disabled={cargando}>
              Atrás
            </Boton>
            <span className="ui-modal__footer-sep" />
            <Boton tipo="secondary" onClick={onCerrar} disabled={cargando}>
              Cancelar
            </Boton>
            <Boton
              tipo="primary"
              onClick={() => void onContinuarCampos()}
              disabled={cargando || claveIdx === null}
            >
              {cargando ? "Generando…" : "Continuar"}
            </Boton>
          </div>
        </div>
      )}

      {fase === "validar" && (
        <div className="wiz-paso">
          {!validacion ? (
            <p className="muted">Validando…</p>
          ) : validacion.ok ? (
            <>
              <p className="wiz-validacion-ok">
                ✓ El archivo se puede reconstruir byte a byte con este formato.
              </p>
              <p className="muted">
                {validacion.n_registros} registro(s) · {validacion.n_visibles} campo(s)
                visible(s) · {validacion.n_ocultos} campo(s) oculto(s)
              </p>
            </>
          ) : (
            <>
              <p className="wiz-validacion-error">✗ {validacion.error_msg}</p>
              {validacion.primer_diff_byte !== null && (
                <p className="muted">Primera diferencia en el byte {validacion.primer_diff_byte}.</p>
              )}
            </>
          )}
          <div className="ui-modal__footer">
            <Boton tipo="ghost" onClick={() => setFase("campos")} disabled={cargando}>
              Volver a campos
            </Boton>
            <span className="ui-modal__footer-sep" />
            <Boton tipo="secondary" onClick={onCerrar} disabled={cargando}>
              Cancelar
            </Boton>
            <Boton
              tipo="primary"
              onClick={() => void onConfirmar()}
              disabled={cargando || !validacion?.ok}
            >
              {cargando ? "Confirmando…" : "Confirmar"}
            </Boton>
          </div>
        </div>
      )}
    </Modal>
  );
}
