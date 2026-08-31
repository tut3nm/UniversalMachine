"""Punto de entrada empaquetado: arranca uvicorn (FastAPI) en un thread de
fondo y abre una ventana pywebview apuntando ahí — un solo proceso, sin
consola, sin depender de Node en la PC del operario (ver PLAN_WEBAPP.md,
"Modelo de proceso"). En desarrollo se usa `run_dev.bat` en cambio (uvicorn
--reload + Vite dev server, dos ventanas), este script es el que empaqueta
`build.bat` con PyInstaller."""

from __future__ import annotations

import socket
import threading

import uvicorn
import webview

from app.main import app


def _puerto_libre() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def main() -> None:
    puerto = _puerto_libre()

    def _run_server():
        uvicorn.run(app, host="127.0.0.1", port=puerto, log_level="warning")

    hilo = threading.Thread(target=_run_server, daemon=True)
    hilo.start()

    webview.create_window(
        "Configurador de Planta",
        f"http://127.0.0.1:{puerto}",
        width=1280,
        height=800,
        min_size=(900, 600),
    )
    webview.start()


if __name__ == "__main__":
    main()
