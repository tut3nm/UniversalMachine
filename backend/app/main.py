from __future__ import annotations

import os
import sys
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from starlette.responses import FileResponse

from app import _bootstrap  # noqa: F401  (side effect: agrega app/core/ a sys.path)
import instancia
import log_config
import paths
import version

from app.routers import consulta as consulta_router
from app.routers import maquinas as maquinas_router
from app.routers import mediciones as mediciones_router
from app.routers import wizard as wizard_router

def _front_dist() -> str:
    """En desarrollo, front/dist (si existe: `npm run build` corrido a
    mano). Empaquetado, PyInstaller lo extrae como recurso 'front_dist' vía
    paths.resource_path (ver build.bat, --add-data)."""
    if getattr(sys, "frozen", False):
        return paths.resource_path("front_dist")
    return os.path.abspath(
        os.path.join(os.path.dirname(__file__), "..", "..", "front", "dist"))


FRONT_DIST = _front_dist()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lock de instancia única simplificado a nivel de TODO el proceso (no
    por máquina, a diferencia de la app Tkinter) — ver PLAN_WEBAPP.md,
    'Los 4 módulos que sí necesitan un ajuste de diseño', punto 1."""
    try:
        instancia.adquirir(paths.app_base_dir())
    except instancia.InstanciaBloqueadaError as e:
        raise RuntimeError(
            f"Ya hay otra instancia de la webapp corriendo en esta PC: {e}") from e
    try:
        yield
    finally:
        instancia.liberar(paths.app_base_dir())


app = FastAPI(title="Configurador de Planta — webapp", lifespan=lifespan)

# En desarrollo, el frontend corre aparte (Vite dev server) y necesita CORS.
# Empaquetado, FastAPI sirve el build de front/dist directamente (sin CORS).
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(maquinas_router.router)
app.include_router(consulta_router.router)
app.include_router(wizard_router.router)
app.include_router(mediciones_router.router)


@app.get("/api/health")
def health():
    return {"status": "ok"}


@app.get("/api/info")
def info():
    """Datos del "Acerca de" y de la barra de estado: los mismos que muestra
    `App.on_about` en el escritorio (máquina232/src/app.py:3998)."""
    return {
        "titulo": "Configurador de Parámetros de Planta",
        "version": version.APP_VERSION,
        "compilacion": version.FECHA_COMPILACION,
        "log_dir": log_config.log_dir(),
    }


if os.path.isdir(FRONT_DIST):
    app.mount("/assets", StaticFiles(directory=os.path.join(FRONT_DIST, "assets")), name="assets")

    @app.get("/{full_path:path}")
    def spa_fallback(full_path: str):
        candidato = os.path.join(FRONT_DIST, full_path)
        if full_path and os.path.isfile(candidato):
            return FileResponse(candidato)
        return FileResponse(os.path.join(FRONT_DIST, "index.html"))
