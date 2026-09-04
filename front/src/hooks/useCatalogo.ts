import { useCallback, useEffect, useRef, useState } from "react";
import { api, type FiltrosTabla, type Registro, type Totales } from "../api";

/** Filas por request. La tabla pide páginas a medida que el operario baja. */
export const TAMANO_PAGINA = 200;

const TOTALES_VACIOS: Totales = { mostrados: 0, reales: 0, total: 0 };

/** Identidad del conjunto filtrado: si cambia, las posiciones de las filas
 *  pasan a significar otra cosa y lo cargado deja de servir. */
export function claveDeFiltros(f: FiltrosTabla): string {
  return JSON.stringify([f.q, [...f.rangos].sort(), f.placeholders, f.orden, f.dir]);
}

/**
 * Catálogo por ventanas: mantiene las filas ya traídas indexadas por su
 * posición en la lista filtrada, y pide al servidor las páginas que faltan
 * a medida que la tabla las necesita.
 *
 * El catálogo más grande de planta supera los 5000 registros, así que la
 * búsqueda, los rangos y el orden los resuelve el backend (ver
 * PLAN_PARIDAD_UI.md, 5.4) y acá solo se administra qué ventana está
 * cargada.
 */
export function useCatalogo(id: string, filtros: FiltrosTabla) {
  const filasRef = useRef(new Map<number, Registro>());
  const paginasRef = useRef(new Set<number>());
  const [version, setVersion] = useState(0);
  const [totales, setTotales] = useState<Totales>(TOTALES_VACIOS);
  const [hash, setHash] = useState<string | null>(null);
  const [advertencias, setAdvertencias] = useState<string[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [listo, setListo] = useState(false);

  const clave = claveDeFiltros(filtros);
  const filtrosRef = useRef(filtros);
  useEffect(() => {
    filtrosRef.current = filtros;
  });

  /** Vuelca una respuesta del servidor en el mapa de filas. */
  const guardar = useCallback((registros: Registro[], offset: number) => {
    registros.forEach((r, i) => filasRef.current.set(offset + i, r));
    setVersion((v) => v + 1);
  }, []);

  const pedirPagina = useCallback(
    async (pagina: number) => {
      if (paginasRef.current.has(pagina)) return;
      paginasRef.current.add(pagina);
      const offset = pagina * TAMANO_PAGINA;
      try {
        const r = await api.listarRegistros(
          id,
          filtrosRef.current,
          offset,
          TAMANO_PAGINA,
        );
        guardar(r.registros, offset);
        setTotales(r.totales);
        setHash(r.hash);
        setAdvertencias(r.advertencias);
        setError(null);
      } catch (e) {
        // Se saca de las páginas "en vuelo" para que un reintento posterior
        // (otro scroll, o recargar) la vuelva a pedir.
        paginasRef.current.delete(pagina);
        setError(String(e));
      }
    },
    [id, guardar],
  );

  /** Se llama desde el scroll de la tabla, con el rango de filas a la vista. */
  const asegurarRango = useCallback(
    (desde: number, hasta: number) => {
      const primera = Math.max(0, Math.floor(desde / TAMANO_PAGINA));
      const ultima = Math.floor(Math.max(desde, hasta) / TAMANO_PAGINA);
      for (let p = primera; p <= ultima; p++) void pedirPagina(p);
    },
    [pedirPagina],
  );

  /** Descarta todo lo cargado y vuelve a traer la primera página. */
  const recargar = useCallback(() => {
    filasRef.current.clear();
    paginasRef.current.clear();
    setListo(false);
    void pedirPagina(0).then(() => setListo(true));
  }, [pedirPagina]);

  // Cambió el filtro, el orden o la máquina: lo cargado ya no sirve porque
  // las posiciones significan otra cosa. Se limpia por ref (no es estado) y
  // se pide la primera página del conjunto nuevo.
  useEffect(() => {
    filasRef.current.clear();
    paginasRef.current.clear();
    let vivo = true;
    const filtrosAhora = filtrosRef.current;
    api
      .listarRegistros(id, filtrosAhora, 0, TAMANO_PAGINA)
      .then((r) => {
        if (!vivo) return;
        paginasRef.current.add(0);
        guardar(r.registros, 0);
        setTotales(r.totales);
        setHash(r.hash);
        setAdvertencias(r.advertencias);
        setError(null);
        setListo(true);
      })
      .catch((e) => vivo && setError(String(e)));
    return () => {
      vivo = false;
    };
  }, [id, clave, guardar]);

  const filaEn = useCallback((n: number) => filasRef.current.get(n), []);

  /** Busca entre las filas ya cargadas la que ocupa `index` en el archivo.
   *  Recorre solo lo que está en memoria (cientos de filas), no el catálogo. */
  const filaPorIndice = useCallback((index: number) => {
    for (const r of filasRef.current.values()) if (r.index === index) return r;
    return undefined;
  }, []);

  return {
    /** Cambia en cada llegada de datos: úsalo como dependencia de render. */
    version,
    listo,
    totales,
    hash,
    setHash,
    advertencias,
    error,
    filaEn,
    filaPorIndice,
    asegurarRango,
    recargar,
  };
}
