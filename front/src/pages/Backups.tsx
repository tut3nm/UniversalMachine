import { Navigate, useParams } from "react-router-dom";

/**
 * Enlace profundo: `/maquinas/:id/backups` abre el modal de Backups sobre
 * la pantalla de la máquina en vez de una ruta con su propia UI, como pide
 * 6.2 de PLAN_PARIDAD_UI.md ("los diálogos son modales sobre la misma
 * pantalla, no rutas separadas").
 */
export default function Backups() {
  const { id } = useParams<{ id: string }>();
  return <Navigate to={`/maquinas/${id}`} state={{ abrir: "backups" }} replace />;
}
