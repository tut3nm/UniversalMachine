import { BrowserRouter, Route, Routes } from "react-router-dom";
import Backups from "./pages/Backups";
import Dashboard from "./pages/Dashboard";
import EditorRecetasMatriz from "./pages/EditorRecetasMatriz";
import GenerarRecetas from "./pages/GenerarRecetas";
import Herramientas from "./pages/Herramientas";
import Historial from "./pages/Historial";
import MaquinaDetalle from "./pages/MaquinaDetalle";
import Mediciones from "./pages/Mediciones";
import RecetasPorArea from "./pages/RecetasPorArea";
import { DialogoProvider, ToastProvider } from "./ui";

export default function App() {
  return (
    <ToastProvider>
      <DialogoProvider>
        <BrowserRouter>
          <Routes>
            <Route path="/" element={<Dashboard />} />
            <Route path="/maquinas/:id" element={<MaquinaDetalle />} />
            <Route path="/maquinas/:id/backups" element={<Backups />} />
            <Route path="/maquinas/:id/historial" element={<Historial />} />
            <Route path="/mediciones" element={<Mediciones />} />
            <Route path="/herramientas" element={<Herramientas />} />
            <Route path="/generador-recetas" element={<GenerarRecetas />} />
            <Route path="/recetas-por-area" element={<RecetasPorArea />} />
            <Route path="/editor-recetas-matriz" element={<EditorRecetasMatriz />} />
          </Routes>
        </BrowserRouter>
      </DialogoProvider>
    </ToastProvider>
  );
}
