"""Punto de entrada empaquetado: arranca uvicorn (FastAPI) en un thread de
fondo y abre una ventana pywebview apuntando ahí — un solo proceso, sin
consola, sin depender de Node en la PC del operario (ver PLAN_WEBAPP.md,
"Modelo de proceso"). En desarrollo se usa `run_dev.bat` en cambio (uvicorn
--reload + Vite dev server, dos ventanas), este script es el que empaqueta
`build.bat` con PyInstaller.

La ventana abre con una pantalla de carga y recien navega a la app cuando
/api/health responde: uvicorn no acepta conexiones hasta terminar el arranque,
y abrir la URL antes daba "error de conexion"."""

from __future__ import annotations

import html
import os
import socket
import threading
import time
import traceback
import urllib.error
import urllib.request

import uvicorn
import webview

_ESPERA_MAX_SEGUNDOS = 120

_PAGINA = (
    "<!doctype html><meta charset='utf-8'><title>Configurador de Planta</title>"
    "<body style=\"font-family:Segoe UI,sans-serif;display:flex;align-items:center;"
    "justify-content:center;height:100vh;margin:0;color:#333\">"
    "<div style='text-align:center;max-width:640px;padding:1rem'>{cuerpo}</div></body>"
)


def _pagina_carga() -> str:
    return _PAGINA.format(cuerpo="<h2>Iniciando…</h2><p>Un momento, se está preparando el sistema.</p>")


def _pagina_error(detalle: str) -> str:
    cuerpo = (
        "<h2>No se pudo iniciar el sistema</h2>"
        "<pre style='text-align:left;white-space:pre-wrap;background:#f3f3f3;padding:.75rem'>"
        f"{html.escape(detalle)}</pre>"
    )
    return _PAGINA.format(cuerpo=cuerpo)


def _puerto_libre() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _servidor_listo(puerto: int) -> bool:
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{puerto}/api/health", timeout=2) as r:
            return r.status == 200
    except (urllib.error.URLError, OSError):
        return False


def main() -> None:
    puerto = _puerto_libre()
    error: list[str] = []

    def _run_server() -> None:
        try:
            from app.main import app

            uvicorn.run(app, host="127.0.0.1", port=puerto, log_level="warning")
        except BaseException:  # noqa: BLE001 - se muestra en la ventana
            error.append(traceback.format_exc())

    hilo = threading.Thread(target=_run_server, daemon=True)
    hilo.start()

    ventana = webview.create_window(
        "Configurador de Planta",
        html=_pagina_carga(),
        width=1280,
        height=800,
        min_size=(900, 600),
    )

    def _esperar_y_navegar() -> None:
        limite = time.time() + _ESPERA_MAX_SEGUNDOS
        while time.time() < limite:
            if error or not hilo.is_alive():
                ventana.load_html(_pagina_error(error[0] if error else "El servidor se cerró al iniciar."))
                return
            if _servidor_listo(puerto):
                ventana.load_url(f"http://127.0.0.1:{puerto}")
                return
            time.sleep(0.3)
        ventana.load_html(_pagina_error("El servidor no respondió a tiempo."))

    webview.start(_esperar_y_navegar)

    # Al cerrar la ventana el thread de uvicorn es daemon y muere sin correr el
    # shutdown de FastAPI: sin esto llama-server.exe quedaba huerfano (1 GB en
    # memoria y el puerto ocupado para el proximo arranque).
    from app.ai import llm

    llm.stop_llama_server()

    import instancia
    import paths

    base = paths.app_base_dir()
    propio = instancia.leer_lock(base)
    if propio and propio.get("pid") == os.getpid():
        instancia.liberar(base)


if __name__ == "__main__":
    main()
