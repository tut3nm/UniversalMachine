import { BrowserRouter, Route, Routes } from "react-router-dom";
import Backups from "./pages/Backups";
import Dashboard from "./pages/Dashboard";
import Historial from "./pages/Historial";
import MaquinaDetalle from "./pages/MaquinaDetalle";
import Mediciones from "./pages/Mediciones";
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
          </Routes>
        </BrowserRouter>
      </DialogoProvider>
    </ToastProvider>
  );
}
