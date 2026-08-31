import { BrowserRouter, Route, Routes } from "react-router-dom";
import Dashboard from "./pages/Dashboard";
import MaquinaDetalle from "./pages/MaquinaDetalle";
import "./App.css";

export default function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/" element={<Dashboard />} />
        <Route path="/maquinas/:id" element={<MaquinaDetalle />} />
      </Routes>
    </BrowserRouter>
  );
}
