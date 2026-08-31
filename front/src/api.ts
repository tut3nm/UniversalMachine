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
  index: number;
  es_placeholder: boolean;
  [campo: string]: unknown;
}

export interface Campo {
  nombre_interno: string;
  rol: string;
  titulo_ui: string;
  tipo: string;
  visible: boolean;
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
  listarMaquinas: () => req<ResumenMaquina[]>("/api/maquinas"),
  obtenerMaquina: (id: string) =>
    req<{ id: string; nombre: string; descripcion: string; campos: Campo[] }>(
      `/api/maquinas/${id}`,
    ),
  listarRegistros: (id: string) =>
    req<{ registros: Registro[]; total: number; reales: number; hash: string | null }>(
      `/api/maquinas/${id}/registros`,
    ),
  crearRegistro: (id: string, valores: Record<string, unknown>, hash?: string | null) =>
    req(`/api/maquinas/${id}/registros`, {
      method: "POST",
      body: JSON.stringify({ valores, hash_esperado: hash ?? null }),
    }),
  actualizarRegistro: (
    id: string,
    index: number,
    valores: Record<string, unknown>,
    hash?: string | null,
  ) =>
    req(`/api/maquinas/${id}/registros/${index}`, {
      method: "PUT",
      body: JSON.stringify({ valores, hash_esperado: hash ?? null }),
    }),
  eliminarRegistro: (id: string, index: number, hash?: string | null) =>
    req(`/api/maquinas/${id}/registros/${index}`, {
      method: "DELETE",
      body: JSON.stringify({ hash_esperado: hash ?? null }),
    }),
  salud: (id: string) =>
    req<{ hallazgos: { tipo: string; idx: number; code: string; mensaje: string }[] }>(
      `/api/maquinas/${id}/salud`,
    ),
  listarBackups: (id: string) => req<BackupInfo[]>(`/api/maquinas/${id}/backups`),
  restaurarBackup: (id: string, nombre: string) =>
    req(`/api/maquinas/${id}/backups/${encodeURIComponent(nombre)}/restaurar`, {
      method: "POST",
    }),
  listarHistorial: (id: string) => req<EventoHistorial[]>(`/api/maquinas/${id}/historial`),
  diferencias: (id: string) => req<{ diffs: DiffRegistro[] }>(`/api/maquinas/${id}/diferencias`),
};

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
