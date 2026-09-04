import { StrictMode } from "react";
import { createRoot } from "react-dom/client";

// Tipografía empaquetada con la app (no CDN): la PC de planta puede no
// tener internet. Vite copia los .woff2 al build y reescribe las rutas.
import "@fontsource/ibm-plex-sans/latin-400.css";
import "@fontsource/ibm-plex-sans/latin-500.css";
import "@fontsource/ibm-plex-sans/latin-600.css";
import "@fontsource/ibm-plex-mono/latin-400.css";

import "./styles/tokens.css";
import "./styles/base.css";
import "./styles/ui.css";

import App from "./App.tsx";

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <App />
  </StrictMode>,
);
