import { useEffect, useRef, useState } from "react";
import {
  api,
  type ArchivosAsistente,
  type PantallaAsistente,
  type RespuestaAsistente,
  type RespuestaReconocimiento,
} from "../api";
import HoverCard from "./HoverCard";
import PlanCard from "./PlanCard";

interface CardPrompt {
  titulo: string;
  texto: string;
  ayuda: string;
}

/** Cada pantalla ofrece indicaciones sobre SUS archivos: el asistente no
 *  deriva a otra pantalla ni explica el sistema (PLAN_ASISTENTE_IA.md, 12). */
const CONFIG: Record<
  PantallaAsistente,
  { cards: CardPrompt[]; placeholder: string; archivos: Record<string, string> }
> = {
  mediciones: {
    archivos: { datos: "el archivo de datos" },
    placeholder: "Ej: la primera tabla va de la fila 1 a la 12 y la segunda de la 14 a la 212",
    cards: [
      {
        titulo: "Indicar las tablas",
        texto: "La primera tabla va de la fila X a la Y y la segunda de la fila Z a la W.",
        ayuda:
          "Reemplazá X, Y, Z y W por los números de fila del archivo. La primera fila de cada tabla se toma como nombres de columna.",
      },
      {
        titulo: "Solo una tabla",
        texto: "Solo quiero la tabla que va de la fila X a la Y.",
        ayuda: "El Excel sale con una sola hoja, con las filas que indiques.",
      },
      {
        titulo: "Cambiar el separador",
        texto: "Las columnas están separadas por punto y coma.",
        ayuda: "Sirve si el archivo usa ; o tabulación en vez de coma.",
      },
    ],
  },
  recetas_por_area: {
    archivos: { listado: "el listado" },
    placeholder: "Ej: generá solo las recetas .15 y .17",
    cards: [
      {
        titulo: "Solo algunos sufijos",
        texto: "Generá solo las recetas .15 y .17.",
        ayuda: "Limita cada fila a las variantes que nombres, en vez de todas las del catálogo de su área.",
      },
      {
        titulo: "Solo un área",
        texto: "Generá solo las filas HD.",
        ayuda: "Filtra el listado por un valor que exista en alguna de sus columnas.",
      },
      {
        titulo: "Nombrar con otra columna",
        texto: "Nombrá los archivos con el amortiguador.",
        ayuda: "Cambia la columna que forma el nombre de cada archivo (se le agrega el sufijo y .def.txt).",
      },
      {
        titulo: "Agrupar en carpetas",
        texto: "Agrupá los archivos por área.",
        ayuda: "Arma una carpeta dentro del .zip por cada valor de la columna que nombres.",
      },
    ],
  },
  plantilla: {
    archivos: { plantilla: "la plantilla", listado: "el listado" },
    placeholder: "Ej: el código lo llena la columna amortiguador",
    cards: [
      {
        titulo: "Qué columna llena un campo",
        texto: "El campo de la línea X lo llena la columna Y.",
        ayuda:
          "Indica qué columna del listado va en un campo {...} de la plantilla, si el comentario // de esa línea no lo dice.",
      },
      {
        titulo: "Nombre de archivo",
        texto: "El nombre de cada archivo sale de la columna Y.",
        ayuda: "Elige la columna del listado que da el nombre a cada archivo generado.",
      },
      {
        titulo: "Solo algunas filas",
        texto: "Generá solo las filas HD.",
        ayuda: "Filtra el listado por un valor que exista en alguna de sus columnas.",
      },
    ],
  },
};

type Mensaje =
  | { autor: "usuario"; texto: string }
  | { autor: "asistente"; texto: string; respuesta: RespuestaAsistente }
  | { autor: "asistente"; texto: string; error: string };

/**
 * Panel lateral colapsable del asistente embebido. Trabaja sobre los
 * archivos que la pantalla ya tiene cargados: lo que el usuario escribe se
 * traduce en ajustes sobre esos archivos, que la tarjeta muestra antes de
 * generar nada.
 */
export default function AsistentePanel({
  pantalla,
  archivos,
}: {
  pantalla: PantallaAsistente;
  archivos: ArchivosAsistente;
}) {
  const config = CONFIG[pantalla];
  const [abierto, setAbierto] = useState(false);
  const [estadoIa, setEstadoIa] = useState<{ disponible: boolean; mensaje: string } | null>(null);
  const [texto, setTexto] = useState("");
  const [mensajes, setMensajes] = useState<Mensaje[]>([]);
  const [enviando, setEnviando] = useState(false);
  const [reconocimiento, setReconocimiento] = useState<RespuestaReconocimiento | null>(null);
  const [reconocimientoDescartado, setReconocimientoDescartado] = useState(false);
  const listaRef = useRef<HTMLDivElement>(null);

  const faltan = Object.entries(config.archivos)
    .filter(([clave]) => !archivos[clave as keyof ArchivosAsistente])
    .map(([, nombre]) => nombre);

  useEffect(() => {
    if (!abierto || estadoIa) return;
    api
      .estadoAsistente()
      .then((s) => setEstadoIa({ disponible: s.disponible, mensaje: s.mensaje }))
      .catch((e) => setEstadoIa({ disponible: false, mensaje: String(e) }));
  }, [abierto, estadoIa]);

  // Memoria de formatos (PLAN_MEMORIA_FORMATOS.md): mediciones, plantilla y
  // recetas por area. Al tener los archivos de la pantalla, se intenta
  // reconocer sin pedirle nada al usuario; si coincide, la tarjeta sale
  // directo.
  const tieneMemoria =
    pantalla === "mediciones" || pantalla === "plantilla" || pantalla === "recetas_por_area";
  useEffect(() => {
    setReconocimiento(null);
    setReconocimientoDescartado(false);
    if (!tieneMemoria || faltan.length > 0) return;
    let cancelado = false;
    api
      .reconocerAsistente(pantalla, archivos)
      .then((r) => {
        if (!cancelado) setReconocimiento(r);
      })
      .catch(() => {
        if (!cancelado) setReconocimiento(null);
      });
    return () => {
      cancelado = true;
    };
  }, [pantalla, archivos.datos, archivos.plantilla, archivos.listado]);

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
      const respuesta = await api.interpretarAsistente(pantalla, pedido, archivos);
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
          {faltan.length > 0 && (
            <p className="muted asistente-panel__aviso">
              Cargá {faltan.join(" y ")} en esta pantalla: el asistente trabaja sobre esos archivos.
            </p>
          )}

          {reconocimiento?.coincidencia === "unica" && !reconocimientoDescartado && (
            <div className="asistente-panel__reconocido">
              <p className="muted">
                Reconocido como <strong>{reconocimiento.formato?.nombre}</strong>.{" "}
                <button
                  type="button"
                  className="ui-btn ui-btn--sm"
                  onClick={() => setReconocimientoDescartado(true)}
                >
                  No es este formato
                </button>
              </p>
              <PlanCard respuesta={reconocimiento as RespuestaAsistente} texto="" archivos={archivos} />
            </div>
          )}
          {reconocimiento?.coincidencia === "varias" && !reconocimientoDescartado && (
            <p className="muted asistente-panel__aviso">
              Podría ser uno de estos formatos ya guardados:{" "}
              {reconocimiento.candidatos.map((c) => c.nombre).join(", ")}. Contame cómo se divide tu
              archivo para confirmar cuál es.
            </p>
          )}

          <div className="hover-card-fila">
            {config.cards.map((c) => (
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
                Contame cómo es tu archivo o qué querés cambiar del resultado, o elegí una de las
                tarjetas de arriba. Antes de generar, te muestro qué se va a hacer.
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
                  <PlanCard respuesta={m.respuesta} texto={m.texto} archivos={archivos} />
                </div>
              ),
            )}
            {enviando && <div className="chat-burbuja chat-burbuja--asistente muted">Interpretando…</div>}
          </div>

          <div className="asistente-panel__input">
            <textarea
              rows={2}
              placeholder={config.placeholder}
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
