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
  restaurarBackup: (id: string, nombre: string) =>
    req(`/api/maquinas/${id}/backups/${encodeURIComponent(nombre)}/restaurar`, {
      method: "POST",
    }),
  listarHistorial: (id: string) => req<EventoHistorial[]>(`/api/maquinas/${id}/historial`),
  diferencias: (id: string) => req<{ diffs: DiffRegistro[] }>(`/api/maquinas/${id}/diferencias`),
  estadoIA: () => req<{ disponible: boolean; mensaje: string }>("/api/mediciones/estado"),
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
}

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

export interface DiffRegistro {
  tipo: string;
  clave: string;
  [k: string]: unknown;
}
