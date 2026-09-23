const BASE = ""; // mismo origen en producción (FastAPI sirve el build); en dev usa el proxy de Vite

export interface ResumenMaquina {
  id: string;
  nombre: string;
  ultima_modificacion: string | null;
  cantidad_registros: number | null;
  duplicados_pendientes: number | null;
  alertas_salud: number | null;
  error: string | null;
}

export interface Registro {
  /** Posición real en el archivo. Es la que se manda al mutar. */
  index: number;
  /** Posición en la lista ya filtrada y ordenada (1 en adelante). */
  pos: number;
  es_placeholder: boolean;
  [campo: string]: unknown;
}

/** Rango numérico de un campo, serializado como lo espera el backend. */
export function rangoATexto(campo: string, min: string, max: string): string {
  return `${campo}:${min.trim()}:${max.trim()}`;
}

/** El formato `{campo: [min, max]}` de un preset guardado, aplanado al
 *  mismo `"campo:min:max"[]` que usa el resto de la app. */
export function rangosDeFiltroAStrings(
  rangos: Record<string, [number | null, number | null]>,
): string[] {
  return Object.entries(rangos).map(([campo, [min, max]]) =>
    rangoATexto(campo, min == null ? "" : String(min), max == null ? "" : String(max)),
  );
}

export interface FiltrosTabla {
  q: string;
  /** Cada entrada es "campo:min:max"; los extremos pueden ir vacíos. */
  rangos: string[];
  placeholders: boolean;
  orden: string | null;
  dir: "asc" | "desc";
}

export const FILTROS_VACIOS: FiltrosTabla = {
  q: "",
  rangos: [],
  placeholders: false,
  orden: null,
  dir: "asc",
};

export interface Totales {
  mostrados: number;
  reales: number;
  total: number;
}

export interface RespuestaRegistros {
  registros: Registro[];
  ventana: { offset: number; limit: number };
  totales: Totales;
  advertencias: string[];
  hash: string | null;
}

export interface Hallazgo {
  tipo: "fuera_de_rango" | "duplicado" | "campo_vacio" | string;
  idx: number;
  code: string;
  mensaje: string;
}

export interface RespuestaSalud {
  hallazgos: Hallazgo[];
  slots_libres: number;
}

/** Filtro frecuente guardado por máquina (búsqueda + rangos numéricos). */
export interface FiltroGuardado {
  nombre: string;
  busqueda: string;
  /** {nombre_interno: [minimo, maximo]}, cualquiera de los dos puede ser null. */
  rangos: Record<string, [number | null, number | null]>;
}

function queryFiltros(f: FiltrosTabla): URLSearchParams {
  const p = new URLSearchParams();
  if (f.q) p.set("q", f.q);
  for (const r of f.rangos) p.append("rango", r);
  if (f.placeholders) p.set("placeholders", "true");
  if (f.orden) {
    p.set("orden", f.orden);
    p.set("dir", f.dir);
  }
  return p;
}

export interface Campo {
  nombre_interno: string;
  rol: string;
  titulo_ui: string;
  tipo: string;
  visible: boolean;
  etiqueta?: string;
  min?: number | null;
  max?: number | null;
  default?: unknown;
  formato?: Record<string, unknown>;
}

export interface DetalleMaquina {
  id: string;
  nombre: string;
  descripcion: string;
  extension: string;
  orientacion: string;
  archivo_inicial: string;
  tiene_placeholders: boolean;
  tiene_duplicados: boolean;
  campos: Campo[];
}

export interface InfoApp {
  titulo: string;
  version: string;
  compilacion: string;
  log_dir: string;
}

export const TIPOS_NUMERICOS = ["entero", "entero_ceros", "decimal"];

export function esNumerico(campo: Campo): boolean {
  return TIPOS_NUMERICOS.includes(campo.tipo);
}

/** Nombre de archivo del header Content-Disposition de una descarga, o un
 *  default si el header no vino o no matchea (nunca debería pasar, pero un
 *  .zip/.xlsx igual sirve sin el nombre "lindo"). */
function _nombreDesdeContentDisposition(res: Response, porDefecto: string): string {
  const match = /filename="?([^";]+)"?/.exec(res.headers.get("Content-Disposition") ?? "");
  return match ? match[1] : porDefecto;
}

/** Resumen JSON informativo mandado en un header custom junto a una
 *  descarga (mismo motivo que arriba: el cuerpo de la respuesta es el
 *  archivo, no puede llevar también el JSON). */
function _resumenDesdeHeader<T>(res: Response, header: string, porDefecto: T): T {
  try {
    return JSON.parse(res.headers.get(header) ?? "null") ?? porDefecto;
  } catch {
    return porDefecto;
  }
}

async function req<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    headers: { "Content-Type": "application/json" },
    ...init,
  });
  if (!res.ok) {
    const detail = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(detail.detail ?? `Error ${res.status}`);
  }
  return res.json();
}

export const api = {
  info: () => req<InfoApp>("/api/info"),
  listarMaquinas: () => req<ResumenMaquina[]>("/api/maquinas"),
  obtenerMaquina: (id: string) => req<DetalleMaquina>(`/api/maquinas/${id}`),
  eliminarMaquina: (id: string, confirmacionNombre: string) =>
    req<{ eliminada: boolean }>(`/api/maquinas/${id}`, {
      method: "DELETE",
      body: JSON.stringify({ confirmacion_nombre: confirmacionNombre }),
    }),

  // -- deshacer / rehacer (B3) -------------------------------------------------
  estadoDeshacer: (id: string) => req<EstadoDeshacer>(`/api/maquinas/${id}/undo-state`),
  deshacer: (id: string) =>
    req<EstadoDeshacer & { hash: string; descripcion: string }>(`/api/maquinas/${id}/deshacer`, {
      method: "POST",
    }),
  rehacer: (id: string) =>
    req<EstadoDeshacer & { hash: string; descripcion: string }>(`/api/maquinas/${id}/rehacer`, {
      method: "POST",
    }),
  /** Una ventana del catálogo, ya filtrada y ordenada por el servidor. */
  listarRegistros: (id: string, filtros: FiltrosTabla, offset: number, limit: number) => {
    const p = queryFiltros(filtros);
    p.set("offset", String(offset));
    p.set("limit", String(limit));
    return req<RespuestaRegistros>(`/api/maquinas/${id}/registros?${p}`);
  },
  /** Todos los índices que matchean el filtro actual, en el orden visible. */
  indicesFiltrados: (id: string, filtros: FiltrosTabla) =>
    req<{ indices: number[] }>(
      `/api/maquinas/${id}/registros/indices?${queryFiltros(filtros)}`,
    ),
  crearRegistro: (id: string, valores: Record<string, unknown>, hash?: string | null) =>
    req<{ index: number; registro: Registro; hash: string }>(
      `/api/maquinas/${id}/registros`,
      {
        method: "POST",
        body: JSON.stringify({ valores, hash_esperado: hash ?? null }),
      },
    ),
  actualizarRegistro: (
    id: string,
    index: number,
    valores: Record<string, unknown>,
    hash?: string | null,
  ) =>
    req<{ index: number; registro: Registro; hash: string }>(
      `/api/maquinas/${id}/registros/${index}`,
      {
        method: "PUT",
        body: JSON.stringify({ valores, hash_esperado: hash ?? null }),
      },
    ),
  eliminarRegistro: (id: string, index: number, hash?: string | null) =>
    req<{ hash: string }>(`/api/maquinas/${id}/registros/${index}`, {
      method: "DELETE",
      body: JSON.stringify({ hash_esperado: hash ?? null }),
    }),
  salud: (id: string) => req<RespuestaSalud>(`/api/maquinas/${id}/salud`),
  /** Aplica un mismo valor a un campo de varios registros de una sola vez. */
  editarEnMasa: (
    id: string,
    indices: number[],
    campo: string,
    valor: string,
    hash?: string | null,
  ) =>
    req<{ modificados: number; hash: string }>(`/api/maquinas/${id}/registros/bulk-edit`, {
      method: "POST",
      body: JSON.stringify({ indices, campo, valor, hash_esperado: hash ?? null }),
    }),
  /** Baja de varios registros como una sola operación. */
  eliminarEnMasa: (id: string, indices: number[], hash?: string | null) =>
    req<{ eliminados: number; hash: string }>(`/api/maquinas/${id}/registros/bulk-delete`, {
      method: "POST",
      body: JSON.stringify({ indices, hash_esperado: hash ?? null }),
    }),
  listarFiltros: (id: string) => req<FiltroGuardado[]>(`/api/maquinas/${id}/filtros`),
  guardarFiltro: (id: string, nombre: string, busqueda: string, rangos: string[]) =>
    req<FiltroGuardado[]>(`/api/maquinas/${id}/filtros`, {
      method: "POST",
      body: JSON.stringify({ nombre, busqueda, rangos }),
    }),
  eliminarFiltro: (id: string, nombre: string) =>
    req<FiltroGuardado[]>(`/api/maquinas/${id}/filtros/${encodeURIComponent(nombre)}`, {
      method: "DELETE",
    }),
  listarBackups: (id: string) => req<BackupInfo[]>(`/api/maquinas/${id}/backups`),
  backupPreview: (id: string, nombre: string) =>
    req<VistaPreviaBackup>(
      `/api/maquinas/${id}/backups/${encodeURIComponent(nombre)}/preview`,
    ),
  restaurarBackup: (id: string, nombre: string) =>
    req<{ hash: string }>(`/api/maquinas/${id}/backups/${encodeURIComponent(nombre)}/restaurar`, {
      method: "POST",
    }),
  restaurarOriginal: (id: string) =>
    req<{ hash: string }>(`/api/maquinas/${id}/restaurar-original`, { method: "POST" }),
  listarHistorial: (id: string, filtros?: FiltrosHistorial) =>
    req<EventoHistorial[]>(`/api/maquinas/${id}/historial?${queryHistorial(filtros)}`),
  diferencias: (id: string) => req<{ diffs: DiffRegistro[] }>(`/api/maquinas/${id}/diferencias`),
  /** URL de descarga directa: no pasa por `req`, se usa en un `<a href>` o
   *  `window.location`, igual que la exportación del escritorio abre un
   *  selector de archivo en vez de devolver datos al programa. */
  exportarUrl: (id: string, cual: "actual" | "original") =>
    `${BASE}/api/maquinas/${id}/exportar?cual=${cual}`,
  historialInformeCsvUrl: (id: string, filtros?: FiltrosHistorial) =>
    `${BASE}/api/maquinas/${id}/historial/informe.csv?${queryHistorial(filtros)}`,
  diferenciasInformeCsvUrl: (id: string, tipos?: string[]) => {
    const p = new URLSearchParams();
    for (const t of tipos ?? []) p.append("tipo", t);
    return `${BASE}/api/maquinas/${id}/diferencias/informe.csv?${p}`;
  },
  // -- duplicados (B4) -------------------------------------------------------
  listarDuplicados: (id: string) => req<RespuestaDuplicados>(`/api/maquinas/${id}/duplicados`),
  marcarNoDuplicado: (id: string, code: string) =>
    req<RespuestaDuplicados>(`/api/maquinas/${id}/duplicados/no-duplicado`, {
      method: "POST",
      body: JSON.stringify({ code }),
    }),
  eliminarDuplicados: (id: string, indices: number[], hash?: string | null) =>
    req<{ eliminados: number; hash: string }>(`/api/maquinas/${id}/duplicados/eliminar`, {
      method: "POST",
      body: JSON.stringify({ indices, hash_esperado: hash ?? null }),
    }),

  // -- importación desde Excel/CSV (B6) ---------------------------------------
  importIniciar: async (id: string, archivo: File): Promise<ImportInicio> => {
    const form = new FormData();
    form.append("file", archivo);
    const res = await fetch(`${BASE}/api/maquinas/${id}/import/start`, {
      method: "POST",
      body: form,
    });
    if (!res.ok) {
      const detail = await res.json().catch(() => ({ detail: res.statusText }));
      throw new Error(detail.detail ?? `Error ${res.status}`);
    }
    return res.json();
  },
  importElegirHoja: (id: string, importId: string, hoja: string) =>
    req<ImportHoja>(`/api/maquinas/${id}/import/hoja`, {
      method: "POST",
      body: JSON.stringify({ import_id: importId, hoja }),
    }),
  importMapear: (id: string, importId: string, mapeo: Record<string, string>) =>
    req<ImportMapeoResultado>(`/api/maquinas/${id}/import/mapping`, {
      method: "POST",
      body: JSON.stringify({ import_id: importId, mapeo }),
    }),
  importAplicar: (
    id: string,
    importId: string,
    diffs: string[],
    nuevos: string[],
    obsoletos: string[],
    hash?: string | null,
  ) =>
    req<{ hash: string; modificados: number; nuevos: number; eliminados: number }>(
      `/api/maquinas/${id}/import/apply`,
      {
        method: "POST",
        body: JSON.stringify({
          import_id: importId,
          diffs,
          nuevos,
          obsoletos,
          hash_esperado: hash ?? null,
        }),
      },
    ),

  // -- wizard de alta/edición de máquina (4 pasos) -----------------------------
  wizardIniciarAlta: async (archivo: File): Promise<WizardInicio> => {
    const form = new FormData();
    form.append("file", archivo);
    const res = await fetch(`${BASE}/api/wizard/start`, { method: "POST", body: form });
    if (!res.ok) {
      const detail = await res.json().catch(() => ({ detail: res.statusText }));
      throw new Error(detail.detail ?? `Error ${res.status}`);
    }
    return res.json();
  },
  wizardIniciarEdicion: (profileId: string) =>
    req<WizardInicio>(`/api/wizard/start?profile_id=${encodeURIComponent(profileId)}`, {
      method: "POST",
    }),
  wizardClasificar: (wizardId: string, orientacion: "columnas" | "filas", primeraCol = 1) =>
    req<WizardClasificacion>("/api/wizard/classify-rows", {
      method: "POST",
      body: JSON.stringify({ wizard_id: wizardId, orientacion, primera_col: primeraCol }),
    }),
  wizardBuildProfile: (
    wizardId: string,
    machineId: string,
    nombre: string,
    descripcion: string,
    claveIdx: number,
    filas: FilaWizardIn[],
  ) =>
    req<PerfilWizard>("/api/wizard/build-profile", {
      method: "POST",
      body: JSON.stringify({
        wizard_id: wizardId,
        machine_id: machineId,
        nombre,
        descripcion,
        clave_idx: claveIdx,
        filas,
      }),
    }),
  wizardValidar: (wizardId: string) =>
    req<WizardValidacion>("/api/wizard/validate", {
      method: "POST",
      body: JSON.stringify({ wizard_id: wizardId }),
    }),
  wizardConfirmar: (wizardId: string) =>
    req<{ machine_id: string; perfil_path: string }>("/api/wizard/confirm", {
      method: "POST",
      body: JSON.stringify({ wizard_id: wizardId }),
    }),

  previsualizarPlantillasMasivas: async (
    plantilla: File,
    listado: File,
  ): Promise<ReportePlantillasMasivas> => {
    const form = new FormData();
    form.append("plantilla", plantilla);
    form.append("listado", listado);
    const res = await fetch(`${BASE}/api/plantillas-masivas/previsualizar`, {
      method: "POST",
      body: form,
    });
    if (!res.ok) {
      const detail = await res.json().catch(() => ({ detail: res.statusText }));
      throw new Error(detail.detail ?? `Error ${res.status}`);
    }
    return res.json();
  },
  generarPlantillasMasivas: async (plantilla: File, listado: File): Promise<Blob> => {
    const form = new FormData();
    form.append("plantilla", plantilla);
    form.append("listado", listado);
    const res = await fetch(`${BASE}/api/plantillas-masivas/generar`, {
      method: "POST",
      body: form,
    });
    if (!res.ok) {
      const detail = await res.json().catch(() => ({ detail: res.statusText }));
      throw new Error(detail.detail ?? `Error ${res.status}`);
    }
    return res.blob();
  },

  previsualizarRecetasPorArea: async (listado: File): Promise<ReporteRecetasPorArea> => {
    const form = new FormData();
    form.append("listado", listado);
    const res = await fetch(`${BASE}/api/recetas-por-area/previsualizar`, {
      method: "POST",
      body: form,
    });
    if (!res.ok) {
      const detail = await res.json().catch(() => ({ detail: res.statusText }));
      throw new Error(detail.detail ?? `Error ${res.status}`);
    }
    return res.json();
  },
  auditarRecetasPorArea: () =>
    req<ReporteAuditoriaRecetas>("/api/recetas-por-area/auditar", { method: "POST" }),
  generarRecetasPorArea: async (listado: File): Promise<Blob> => {
    const form = new FormData();
    form.append("listado", listado);
    const res = await fetch(`${BASE}/api/recetas-por-area/generar`, {
      method: "POST",
      body: form,
    });
    if (!res.ok) {
      const detail = await res.json().catch(() => ({ detail: res.statusText }));
      throw new Error(detail.detail ?? `Error ${res.status}`);
    }
    return res.blob();
  },

  estadoIA: () => req<{ disponible: boolean; mensaje: string }>("/api/mediciones/estado"),

  // -- asistente embebido (DSL de operaciones) --------------------------------
  estadoAsistente: () =>
    req<EstadoAsistente>("/api/asistente/estado"),
  interpretarAsistente: async (texto: string, listado: File | null): Promise<RespuestaInterpretar> => {
    const form = new FormData();
    form.append("texto", texto);
    if (listado) form.append("listado", listado);
    const res = await fetch(`${BASE}/api/asistente/interpretar`, { method: "POST", body: form });
    if (!res.ok) {
      const detail = await res.json().catch(() => ({ detail: res.statusText }));
      throw new Error(detail.detail ?? `Error ${res.status}`);
    }
    return res.json();
  },
  ejecutarAsistente: async (
    programa: ProgramaAsistente[],
    listado: File,
    texto: string,
  ): Promise<{ blob: Blob; nombreArchivo: string; resumen: ResumenEjecucionAsistente }> => {
    const form = new FormData();
    form.append("programa", JSON.stringify(programa));
    form.append("listado", listado);
    form.append("texto", texto);
    const res = await fetch(`${BASE}/api/asistente/ejecutar`, { method: "POST", body: form });
    if (!res.ok) {
      const detail = await res.json().catch(() => ({ detail: res.statusText }));
      throw new Error(detail.detail ?? `Error ${res.status}`);
    }
    const nombreArchivo = _nombreDesdeContentDisposition(res, "asistente.zip");
    const resumen = _resumenDesdeHeader<ResumenEjecucionAsistente>(res, "X-Asistente-Resumen", {
      cantidad_archivos: 0, advertencias: [],
    });
    const blob = await res.blob();
    return { blob, nombreArchivo, resumen };
  },
  // -- editor de recetas tipo matriz (PLAN_EDITOR_RECETAS_MATRIZ.md) ----------
  editorRecetasExportar: async (csv: File): Promise<{ blob: Blob; nombreArchivo: string; resumen: ResumenExportarEditorRecetas }> => {
    const form = new FormData();
    form.append("csv", csv);
    const res = await fetch(`${BASE}/api/editor-recetas/exportar`, { method: "POST", body: form });
    if (!res.ok) {
      const detail = await res.json().catch(() => ({ detail: res.statusText }));
      throw new Error(detail.detail ?? `Error ${res.status}`);
    }
    const nombreArchivo = _nombreDesdeContentDisposition(res, "editable.xlsx");
    const resumen = _resumenDesdeHeader<ResumenExportarEditorRecetas>(res, "X-Editor-Recetas-Resumen", {
      n_productos: 0, n_parametros: 0,
    });
    const blob = await res.blob();
    return { blob, nombreArchivo, resumen };
  },
  editorRecetasAplicar: async (csvOriginal: File, xlsxEditado: File): Promise<ReporteAplicarEditorRecetas> => {
    const form = new FormData();
    form.append("csv_original", csvOriginal);
    form.append("xlsx_editado", xlsxEditado);
    const res = await fetch(`${BASE}/api/editor-recetas/aplicar`, { method: "POST", body: form });
    if (!res.ok) {
      const detail = await res.json().catch(() => ({ detail: res.statusText }));
      throw new Error(detail.detail ?? `Error ${res.status}`);
    }
    return res.json();
  },
  editorRecetasAplicarYDescargar: async (
    csvOriginal: File,
    xlsxEditado: File,
  ): Promise<{ blob: Blob; nombreArchivo: string; resumen: ResumenAplicarEditorRecetas }> => {
    const form = new FormData();
    form.append("csv_original", csvOriginal);
    form.append("xlsx_editado", xlsxEditado);
    const res = await fetch(`${BASE}/api/editor-recetas/aplicar/descargar`, { method: "POST", body: form });
    if (!res.ok) {
      const detail = await res.json().catch(() => ({ detail: res.statusText }));
      throw new Error(detail.detail ?? `Error ${res.status}`);
    }
    const nombreArchivo = _nombreDesdeContentDisposition(res, "actualizado.csv");
    const resumen = _resumenDesdeHeader<ResumenAplicarEditorRecetas>(res, "X-Editor-Recetas-Resumen", {
      cantidad_cambios: 0, advertencias: [],
    });
    const blob = await res.blob();
    return { blob, nombreArchivo, resumen };
  },

  procesarMediciones: async (
    archivo: File,
    anotaciones: File | null,
    useAi: boolean,
  ): Promise<ResultadoMediciones> => {
    const form = new FormData();
    form.append("archivo", archivo);
    if (anotaciones) form.append("anotaciones", anotaciones);
    form.append("use_ai", String(useAi));
    const res = await fetch(`${BASE}/api/mediciones/procesar`, { method: "POST", body: form });
    if (!res.ok) {
      const detail = await res.json().catch(() => ({ detail: res.statusText }));
      throw new Error(detail.detail ?? `Error ${res.status}`);
    }
    return res.json();
  },
};

export interface ReportePlantillasMasivas {
  cantidad_archivos: number;
  nombres_archivo: string[];
  lineas_ignoradas: number[];
  columnas_sin_uso: string[];
}

/** Hallazgo de una regla determinista de validacion (sin IA), ver
 *  backend/app/ai/validacion_recetas.py. */
export interface HallazgoValidacion {
  regla: string;
  archivo: string;
  mensaje: string;
}

export interface ReporteRecetasPorArea {
  cantidad_archivos: number;
  areas_usadas: Record<string, number>;
  filas_sin_area: number[];
  nombres_archivo: string[];
  hallazgos_listado: HallazgoValidacion[];
  hallazgos_catalogo: HallazgoValidacion[];
}

export interface ReporteAuditoriaRecetas {
  hallazgos: HallazgoValidacion[];
}

export interface ResultadoMediciones {
  out_filename: string;
  records: number;
  fields: number;
  configs: number;
  period: number;
  unparsed: number;
  ai_messages: string[];
  download_url: string;
}

export interface BackupInfo {
  nombre: string;
  ruta: string;
  timestamp: string;
  tamano_bytes: number;
  integridad_ok: boolean;
}

export interface VistaPreviaBackup {
  integridad_ok: boolean;
  se_perderian: string[];
  se_recuperarian: string[];
  cambiarian: string[];
}

export const ACCION_LABEL: Record<string, string> = {
  alta: "Alta",
  modificacion: "Modificación",
  baja: "Baja",
  importacion: "Importación",
  restauracion: "Restauración",
  limpieza: "Limpieza de metadatos",
};

export interface EventoHistorial {
  timestamp: string;
  usuario: string;
  accion: string;
  clave: string;
  anteriores: Record<string, unknown> | null;
  nuevos: Record<string, unknown> | null;
  origen: string;
  version: string | null;
}

export interface FiltrosHistorial {
  codigo?: string;
  accion?: string;
  /** Antigüedad máxima en días (7, 30, 90); sin límite si se omite. */
  desde?: number;
}

function queryHistorial(f?: FiltrosHistorial): URLSearchParams {
  const p = new URLSearchParams();
  if (f?.codigo) p.set("codigo", f.codigo);
  if (f?.accion) p.set("accion", f.accion);
  if (f?.desde) p.set("desde", String(f.desde));
  return p;
}

export const TIPO_DIFF_LABEL: Record<string, string> = {
  alta: "Alta",
  baja: "Baja",
  modificacion: "Modificación",
};

export interface DiffRegistro {
  tipo: "alta" | "baja" | "modificacion";
  code: string;
  anteriores: Record<string, unknown> | null;
  nuevos: Record<string, unknown> | null;
  campos_modificados: string[];
}

// -- duplicados (B4) -----------------------------------------------------------
export interface DuplicadoRegistro {
  index: number;
  code: string;
  valores: Record<string, unknown>;
  revisado: boolean;
}

export interface DuplicadoGrupo {
  registros: DuplicadoRegistro[];
}

export interface RespuestaDuplicados {
  grupos: DuplicadoGrupo[];
}

// -- importación desde Excel/CSV (B6) -------------------------------------------
export interface ErrorValidacionApi {
  campo: string;
  titulo_ui: string;
  mensaje: string;
}

export interface ImportHoja {
  hoja: string;
  headers: string[];
  /** {nombre_interno: encabezado sugerido, o null si no hay sugerencia}. */
  sugerencia: Record<string, string | null>;
  preview: unknown[][];
}

export interface ImportInicio extends ImportHoja {
  import_id: string;
  hojas: string[];
}

export interface ImportDiffRegistro {
  idx: number;
  code: string;
  old: Record<string, unknown>;
  new: Record<string, unknown>;
  errores: ErrorValidacionApi[];
  redondeos: string[];
}

export interface ImportNuevoRegistro {
  code: string;
  valores: Record<string, unknown>;
  errores: ErrorValidacionApi[];
  redondeos: string[];
}

export interface ImportObsoleto {
  idx: number;
  code: string;
}

export interface ImportMapeoResultado {
  diffs: ImportDiffRegistro[];
  nuevos: ImportNuevoRegistro[];
  obsoletos: ImportObsoleto[];
  sin_cambios: number;
}

// -- deshacer / rehacer (B3) -----------------------------------------------------
export interface EstadoDeshacer {
  puede_deshacer: boolean;
  puede_rehacer: boolean;
  descripcion_deshacer: string | null;
  descripcion_rehacer: string | null;
}

// -- wizard de alta/edición de máquina (4 pasos) ----------------------------------
export interface WizardInicio {
  wizard_id: string;
  modo: "alta" | "edicion";
  info: Record<string, unknown>;
  n_filas: number;
  n_columnas: number;
  /** Primeras 12 filas crudas del archivo, para la vista previa del paso 1. */
  grid_preview: string[][];
}

export interface FilaClasificada {
  idx: number;
  etiqueta: string;
  /** Primeros valores de esa fila/columna, para que el operario reconozca el dato. */
  muestra: string[];
  kind: "fija" | "dato";
  incluir_default: boolean;
  nombre_default: string;
  titulo_default: string;
  tipo_sugerido: string;
  formato_sugerido: Record<string, unknown>;
}

export interface WizardClasificacion {
  clave_sugerida: number | null;
  filas: FilaClasificada[];
}

export interface FilaWizardIn {
  idx: number;
  incluir: boolean;
  nombre?: string | null;
  titulo?: string | null;
  etiqueta?: string | null;
  tipo: string;
  formato?: Record<string, unknown>;
  min?: number | null;
  max?: number | null;
  default?: unknown;
  kind_override?: string | null;
}

export interface PerfilWizard {
  id: string;
  nombre: string;
  descripcion: string;
  campos: unknown[];
  [k: string]: unknown;
}

export interface WizardValidacion {
  ok: boolean;
  n_registros: number;
  n_visibles: number;
  n_ocultos: number;
  error_msg: string | null;
  primer_diff_byte: number | null;
  orig_len: number | null;
  regen_len: number | null;
}

// -- asistente embebido (DSL de operaciones) --------------------------------
export interface EstadoAsistente {
  disponible: boolean;
  mensaje: string;
  server_activo: boolean;
}

/** Una operacion del programa DSL: ver PLAN_ASISTENTE_IA.md seccion 3.
 *  El front nunca interpreta `args`, solo lo muestra y lo reenvia tal cual
 *  a /ejecutar — el significado de cada operacion vive en el backend. */
export interface ProgramaAsistente {
  op: string;
  args: Record<string, unknown>;
}

export interface RespuestaInterpretar {
  programa: ProgramaAsistente[];
  desconocido: boolean;
  /** Presente cuando `desconocido` es true. */
  mensaje?: string;
  /** Descripcion en criollo de la operacion elegida (para mostrar en la card). */
  descripcion?: string;
  /** La operacion elegida es de otra pantalla (ej. 'tabular_mediciones' pedido
   *  desde 'Recetas por área'): el front ofrece ir a esa pantalla en vez de
   *  intentar ejecutarla aca. */
  requiere_pantalla?: string;
  /** La operacion es 'generar_recetas_por_area' pero esta pantalla todavia no
   *  tiene un listado cargado: hace falta antes de poder armar la vista previa. */
  requiere_listado?: boolean;
  cantidad_archivos?: number;
  advertencias?: string[];
  error_validacion?: string;
  hallazgos?: HallazgoValidacion[];
}

export interface ResumenEjecucionAsistente {
  cantidad_archivos: number;
  advertencias: string[];
}

// -- editor de recetas tipo matriz (PLAN_EDITOR_RECETAS_MATRIZ.md) ----------
export interface ResumenExportarEditorRecetas {
  n_productos: number;
  n_parametros: number;
}

export interface CambioEditorRecetas {
  parametro: string;
  producto: string;
  valor_anterior: string;
  valor_nuevo: string;
}

export interface ReporteAplicarEditorRecetas {
  cantidad_cambios: number;
  cambios: CambioEditorRecetas[];
  advertencias: string[];
  /** true si la autoverificación del motor encontró un problema (ALERTA):
   *  no se ofrece la descarga, ver PLAN_EDITOR_RECETAS_MATRIZ.md sección 2. */
  bloqueado: boolean;
}

export interface ResumenAplicarEditorRecetas {
  cantidad_cambios: number;
  advertencias: string[];
}
