"""Logging de aplicación (Nivel 3.2 del plan de mejoras).

Por qué existe: si algo falla en planta, antes no quedaba ningún rastro —
el diagnóstico dependía de que el operario recordara qué había hecho. Este
módulo configura un logger de archivo con rotación diaria y retención de
30 días en `datos/log/`, y expone un manejador global de excepciones no
capturadas para reemplazar el traceback crudo de Tkinter por un diálogo
con la ruta del log y un botón para copiar el detalle."""

from __future__ import annotations

import logging
import logging.handlers
import os
import sys
import traceback

import paths

LOGGER_NAME = "configurador"
RETENCION_DIAS = 30

_logger: logging.Logger | None = None


def log_dir() -> str:
    d = os.path.join(paths.app_base_dir(), "datos", "log")
    os.makedirs(d, exist_ok=True)
    return d


def configurar_logging() -> logging.Logger:
    """Idempotente: llamarla más de una vez no duplica handlers."""
    global _logger
    if _logger is not None:
        return _logger

    logger = logging.getLogger(LOGGER_NAME)
    logger.setLevel(logging.INFO)

    handler = logging.handlers.TimedRotatingFileHandler(
        os.path.join(log_dir(), "app.log"),
        when="midnight", backupCount=RETENCION_DIAS, encoding="utf-8")
    handler.suffix = "%Y%m%d"
    handler.setFormatter(logging.Formatter(
        "%(asctime)s %(levelname)s %(message)s", datefmt="%Y-%m-%d %H:%M:%S"))
    logger.addHandler(handler)

    _logger = logger
    return logger


def get_logger() -> logging.Logger:
    return _logger or configurar_logging()


def instalar_manejador_excepciones_no_capturadas(on_excepcion) -> None:
    """Reemplaza sys.excepthook: registra la excepción en el log con
    traceback completo y llama a `on_excepcion(texto_detalle)` para que la
    UI muestre un diálogo en vez de dejar morir el proceso con el traceback
    crudo de Tkinter en la consola."""
    logger = get_logger()

    def _hook(exc_type, exc_value, exc_tb):
        detalle = "".join(traceback.format_exception(exc_type, exc_value, exc_tb))
        logger.error("Excepción no capturada:\n%s", detalle)
        try:
            on_excepcion(detalle)
        except Exception:
            logger.error("El manejador de excepciones de la UI también falló:\n%s",
                        traceback.format_exc())

    sys.excepthook = _hook

    # Tkinter no pasa por sys.excepthook para errores en callbacks de
    # eventos (bind, after, etc.) — usa Tk.report_callback_exception.
    try:
        import tkinter as tk
        tk.Tk.report_callback_exception = staticmethod(
            lambda exc_type, exc_value, exc_tb: _hook(exc_type, exc_value, exc_tb))
    except ImportError:
        pass
