import { useEffect, useRef, useState } from "react";
import { api, type RespuestaInterpretar } from "../api";
import HoverCard from "./HoverCard";
import PlanCard from "./PlanCard";

interface CardPrompt {
  titulo: string;
  texto: string;
  ayuda: string;
}

const CARDS: CardPrompt[] = [
  {
    titulo: "Generar recetas por área",
    texto: "Generá las recetas por área de este listado.",
    ayuda:
      "Usa el catálogo de referencia (HD/GPS1/GPS2) para expandir cada fila del listado en todas las variantes de su área.",
  },
  {
    titulo: "Generar desde plantilla",
    texto: "Generá un archivo por fila usando mi plantilla con campos entre llaves.",
    ayuda:
      "Necesita una plantilla de ejemplo con los campos variables marcados entre {...} y un listado con un registro por fila.",
  },
  {
    titulo: "Tabular mediciones de ensayo",
    texto: "Tabulá las mediciones de este ensayo a un Excel.",
    ayuda: "Convierte el archivo crudo del equipo de ensayo en una planilla con los nombres de columna prolijados.",
  },
];

type Mensaje =
  | { autor: "usuario"; texto: string }
  | { autor: "asistente"; texto: string; respuesta: RespuestaInterpretar }
  | { autor: "asistente"; texto: string; error: string };

/**
 * Panel lateral colapsable del asistente embebido. Vive en las 3 pantallas
 * de herramientas (PLAN_ASISTENTE_IA.md seccion 6/7): recibe por props el
 * contexto de pantalla que ya tiene cargado (hoy solo hace falta el listado
 * de recetas, que es lo unico con operaciones finas ejecutables aca mismo).
 */
export default function AsistentePanel({
  pantallaActual,
  listadoRecetas = null,
}: {
  pantallaActual: string;
  listadoRecetas?: File | null;
}) {
  const [abierto, setAbierto] = useState(false);
  const [estadoIa, setEstadoIa] = useState<{ disponible: boolean; mensaje: string } | null>(null);
  const [texto, setTexto] = useState("");
  const [mensajes, setMensajes] = useState<Mensaje[]>([]);
  const [enviando, setEnviando] = useState(false);
  const listaRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!abierto || estadoIa) return;
    api
      .estadoAsistente()
      .then((s) => setEstadoIa({ disponible: s.disponible, mensaje: s.mensaje }))
      .catch((e) => setEstadoIa({ disponible: false, mensaje: String(e) }));
  }, [abierto, estadoIa]);

  useEffect(() => {
    listaRef.current?.scrollTo({ top: listaRef.current.scrollHeight });
  }, [mensajes]);

  const onEnviar = async () => {
    const pedido = texto.trim();
    if (!pedido || enviando) return;
    setEnviando(true);
    setTexto("");
    setMensajes((m) => [...m, { autor: "usuario", texto: pedido }]);
    try {
      const respuesta = await api.interpretarAsistente(pedido, listadoRecetas);
      setMensajes((m) => [...m, { autor: "asistente", texto: pedido, respuesta }]);
    } catch (e) {
      setMensajes((m) => [...m, { autor: "asistente", texto: pedido, error: String(e) }]);
    } finally {
      setEnviando(false);
    }
  };

  return (
    <div className={`asistente-panel ${abierto ? "asistente-panel--abierto" : ""}`}>
      <button
        type="button"
        className="asistente-panel__pestana"
        onClick={() => setAbierto((v) => !v)}
        aria-expanded={abierto}
      >
        {abierto ? "Cerrar asistente ›" : "‹ Asistente"}
      </button>

      {abierto && (
        <div className="asistente-panel__cuerpo">
          <h3>Asistente</h3>
          {estadoIa && !estadoIa.disponible && (
            <p className="error">La IA local no está disponible: {estadoIa.mensaje}</p>
          )}

          <div className="hover-card-fila">
            {CARDS.map((c) => (
              <HoverCard
                key={c.titulo}
                titulo={c.titulo}
                ayuda={c.ayuda}
                onSeleccionar={() => setTexto(c.texto)}
              />
            ))}
          </div>

          <div className="asistente-panel__mensajes" ref={listaRef}>
            {mensajes.length === 0 && (
              <p className="muted">
                Explicá en una frase qué necesitás, o elegí una de las tarjetas de arriba.
              </p>
            )}
            {mensajes.map((m, i) =>
              m.autor === "usuario" ? (
                <div key={i} className="chat-burbuja chat-burbuja--usuario">
                  {m.texto}
                </div>
              ) : "error" in m ? (
                <div key={i} className="chat-burbuja chat-burbuja--asistente">
                  <p className="error">{m.error}</p>
                </div>
              ) : (
                <div key={i} className="chat-burbuja chat-burbuja--asistente">
                  <PlanCard
                    respuesta={m.respuesta}
                    texto={m.texto}
                    listado={listadoRecetas}
                    pantallaActual={pantallaActual}
                  />
                </div>
              ),
            )}
            {enviando && <div className="chat-burbuja chat-burbuja--asistente muted">Interpretando…</div>}
          </div>

          <div className="asistente-panel__input">
            <textarea
              rows={2}
              placeholder="Ej: generá solo las recetas .15 y .17 de las filas HD"
              value={texto}
              onChange={(e) => setTexto(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter" && !e.shiftKey) {
                  e.preventDefault();
                  void onEnviar();
                }
              }}
            />
            <button
              type="button"
              className="ui-btn ui-btn--primary ui-btn--sm"
              onClick={() => void onEnviar()}
              disabled={!texto.trim() || enviando}
            >
              Enviar
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
