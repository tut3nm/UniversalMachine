"""
Conversor de ensayos Fuerza-Velocidad de amortiguadores a Excel.

Aplicacion de escritorio (ventana simple) pensada para un usuario sin
conocimientos de programacion: se elige el archivo .txt que entrega la
maquina de ensayos y se genera un Excel con toda la informacion, ordenada
y con el resultado (OK/NOK) de cada medicion.
"""
from __future__ import annotations

import os
import sys
import queue
import threading
import traceback
from datetime import datetime

import tkinter as tk
from tkinter import filedialog, messagebox, ttk

import parser as core_parser
import excel_writer

APP_TITLE = "Conversor de Ensayos de Amortiguadores a Excel"


def base_dir() -> str:
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))


def log_error(exc: BaseException) -> str:
    log_path = os.path.join(base_dir(), "error.log")
    with open(log_path, "a", encoding="utf-8") as f:
        f.write(f"\n--- {datetime.now().strftime('%d/%m/%Y %H:%M:%S')} ---\n")
        f.write("".join(traceback.format_exception(type(exc), exc, exc.__traceback__)))
    return log_path


def default_output_path(input_path: str) -> str:
    folder = os.path.dirname(input_path)
    name = os.path.splitext(os.path.basename(input_path))[0]
    candidate = os.path.join(folder, f"{name}.xlsx")
    n = 2
    while os.path.exists(candidate):
        candidate = os.path.join(folder, f"{name} ({n}).xlsx")
        n += 1
    return candidate


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title(APP_TITLE)
        self.geometry("760x560")
        self.minsize(680, 520)
        self.configure(bg="#F2F2F2")

        self.selected_file: str | None = None
        self.output_path: str | None = None
        self.msg_queue: queue.Queue = queue.Queue()
        self.worker_running = False

        self._build_ui()
        self.after(100, self._poll_queue)

    # ------------------------------------------------------------------
    # UI
    # ------------------------------------------------------------------
    def _build_ui(self):
        FONT_TITLE = ("Segoe UI", 16, "bold")
        FONT_TEXT = ("Segoe UI", 11)
        FONT_TEXT_B = ("Segoe UI", 11, "bold")
        FONT_BTN = ("Segoe UI", 12, "bold")
        FONT_SMALL = ("Segoe UI", 9)

        self.FONT_TEXT = FONT_TEXT
        self.FONT_TEXT_B = FONT_TEXT_B
        self.FONT_SMALL = FONT_SMALL

        pad = {"padx": 20}

        header = tk.Frame(self, bg="#1F4E78")
        header.pack(fill="x")
        tk.Label(
            header, text=APP_TITLE, font=FONT_TITLE, bg="#1F4E78", fg="white",
            pady=14,
        ).pack(**pad)

        body = tk.Frame(self, bg="#F2F2F2")
        body.pack(fill="both", expand=True, padx=24, pady=18)

        instr = (
            "Pasos a seguir:\n"
            "1) Presioná \"Seleccionar archivo .txt\" y elegí el archivo que entrega "
            "la máquina de ensayos.\n"
            "2) Presioná \"Generar Excel\".\n"
            "3) El Excel se guarda automáticamente en la misma carpeta que el "
            "archivo .txt, y se abre solo al terminar."
        )
        tk.Label(
            body, text=instr, font=FONT_TEXT, bg="#F2F2F2", fg="#333333",
            justify="left", anchor="w", wraplength=680,
        ).pack(fill="x", pady=(0, 16))

        step1 = tk.LabelFrame(body, text=" Paso 1 ", font=FONT_TEXT_B, bg="#F2F2F2", fg="#1F4E78", padx=14, pady=14)
        step1.pack(fill="x", pady=(0, 14))

        self.btn_select = tk.Button(
            step1, text="Seleccionar archivo .txt...", font=FONT_BTN,
            bg="#1F4E78", fg="white", activebackground="#163A5C", activeforeground="white",
            relief="flat", padx=16, pady=10, cursor="hand2",
            command=self.on_select_file,
        )
        self.btn_select.pack(side="left")

        self.lbl_file = tk.Label(
            step1, text="Ningún archivo seleccionado todavía.", font=FONT_TEXT,
            bg="#F2F2F2", fg="#666666", anchor="w",
        )
        self.lbl_file.pack(side="left", padx=(16, 0), fill="x", expand=True)

        step2 = tk.LabelFrame(body, text=" Paso 2 ", font=FONT_TEXT_B, bg="#F2F2F2", fg="#1F4E78", padx=14, pady=14)
        step2.pack(fill="x", pady=(0, 14))

        self.btn_generate = tk.Button(
            step2, text="Generar Excel", font=FONT_BTN,
            bg="#2E7D32", fg="white", activebackground="#1B5E20", activeforeground="white",
            relief="flat", padx=16, pady=10, cursor="hand2",
            state="disabled", command=self.on_generate,
        )
        self.btn_generate.pack(side="left")

        self.progress = ttk.Progressbar(step2, orient="horizontal", mode="determinate", maximum=100)
        self.progress.pack(side="left", fill="x", expand=True, padx=(16, 0))

        self.lbl_status = tk.Label(body, text="", font=FONT_TEXT, bg="#F2F2F2", fg="#333333", anchor="w", justify="left")
        self.lbl_status.pack(fill="x", pady=(4, 10))

        self.result_frame = tk.Frame(body, bg="#FFFFFF", highlightbackground="#CCCCCC", highlightthickness=1)
        self.result_text = tk.Label(
            self.result_frame, text="", font=FONT_TEXT, bg="#FFFFFF", fg="#333333",
            justify="left", anchor="w", wraplength=660,
        )
        self.result_text.pack(fill="x", padx=16, pady=(16, 8), anchor="w")

        btns = tk.Frame(self.result_frame, bg="#FFFFFF")
        btns.pack(fill="x", padx=16, pady=(0, 16))
        self.btn_open_excel = tk.Button(
            btns, text="Abrir Excel", font=FONT_TEXT_B, bg="#1F4E78", fg="white",
            relief="flat", padx=12, pady=6, cursor="hand2", command=self.on_open_excel,
        )
        self.btn_open_excel.pack(side="left")
        self.btn_open_folder = tk.Button(
            btns, text="Abrir carpeta", font=FONT_TEXT_B, bg="#5A6B7B", fg="white",
            relief="flat", padx=12, pady=6, cursor="hand2", command=self.on_open_folder,
        )
        self.btn_open_folder.pack(side="left", padx=(10, 0))

        tk.Label(
            self, text="ZF – Ensayos de Amortiguadores", font=FONT_SMALL, bg="#F2F2F2", fg="#999999",
        ).pack(side="bottom", pady=6)

    # ------------------------------------------------------------------
    # Acciones
    # ------------------------------------------------------------------
    def on_select_file(self):
        initial = os.path.join(os.path.expanduser("~"), "Desktop")
        if not os.path.isdir(initial):
            initial = os.path.expanduser("~")
        path = filedialog.askopenfilename(
            title="Seleccioná el archivo .txt de la máquina de ensayos",
            initialdir=initial,
            filetypes=[("Archivos de texto", "*.txt"), ("Todos los archivos", "*.*")],
        )
        if not path:
            return
        self.selected_file = path
        self.lbl_file.config(text=os.path.basename(path), fg="#1F4E78", font=self.FONT_TEXT_B)
        self.btn_generate.config(state="normal")
        self.result_frame.pack_forget()
        self.lbl_status.config(text="")
        self.progress["value"] = 0

    def on_generate(self):
        if not self.selected_file or self.worker_running:
            return
        self.worker_running = True
        self.btn_select.config(state="disabled")
        self.btn_generate.config(state="disabled")
        self.result_frame.pack_forget()
        self.progress["value"] = 0
        self.lbl_status.config(text="Leyendo archivo...")

        thread = threading.Thread(target=self._worker, args=(self.selected_file,), daemon=True)
        thread.start()

    def _worker(self, path: str):
        try:
            def parse_progress(cur, total):
                pct = (cur / total) * 10 if total else 0
                self.msg_queue.put(("progress", pct, "Leyendo y ordenando datos..."))

            result = core_parser.parse_file(path, progress_callback=parse_progress)

            if len(result.measurements) == 0:
                self.msg_queue.put(("error_msg",
                    "No se encontraron mediciones reconocibles en este archivo.\n\n"
                    "Verificá que sea un archivo .txt generado por la máquina de "
                    "ensayos de Fuerza-Velocidad (con bloques de configuración y "
                    "mediciones)."))
                return

            output_path = default_output_path(path)

            def excel_progress(cur, total):
                pct = 10 + (cur / total) * 90 if total else 10
                self.msg_queue.put(("progress", pct, "Generando Excel..."))

            excel_writer.write_excel(result, output_path, path, progress_callback=excel_progress)

            total = len(result.measurements)
            total_ok = sum(1 for m in result.measurements if m.resultado_general)
            total_nok = total - total_ok
            resumen = {
                "output_path": output_path,
                "total": total,
                "ok": total_ok,
                "nok": total_nok,
                "configs": len(result.configs),
                "warnings": len(result.warnings),
                "anomalias": len(result.date_anomalies),
            }
            self.msg_queue.put(("done", resumen))
        except Exception as exc:  # noqa: BLE001 - se muestra mensaje amigable al usuario
            log_path = log_error(exc)
            self.msg_queue.put(("error_msg",
                "Ocurrió un error inesperado al procesar el archivo.\n\n"
                f"Se guardó el detalle técnico en:\n{log_path}\n\n"
                "Podés enviar ese archivo si necesitás ayuda para resolverlo."))

    def _poll_queue(self):
        try:
            while True:
                msg = self.msg_queue.get_nowait()
                kind = msg[0]
                if kind == "progress":
                    _, pct, text = msg
                    self.progress["value"] = pct
                    self.lbl_status.config(text=text)
                elif kind == "done":
                    self._on_done(msg[1])
                elif kind == "error_msg":
                    self._on_error(msg[1])
        except queue.Empty:
            pass
        self.after(100, self._poll_queue)

    def _on_done(self, resumen: dict):
        self.worker_running = False
        self.btn_select.config(state="normal")
        self.btn_generate.config(state="normal")
        self.progress["value"] = 100
        self.lbl_status.config(text="¡Listo!")
        self.output_path = resumen["output_path"]

        pct_ok = (100 * resumen["ok"] / resumen["total"]) if resumen["total"] else 0
        extra = ""
        if resumen["anomalias"]:
            extra += f"\nAtención: se detectaron {resumen['anomalias']} tramo(s) con fecha inconsistente en el equipo (ver hoja Resumen)."
        if resumen["warnings"]:
            extra += f"\nAtención: {resumen['warnings']} línea(s) del archivo no se pudieron interpretar (ver error.log)."

        self.result_text.config(text=(
            f"Excel generado correctamente:\n{resumen['output_path']}\n\n"
            f"Mediciones procesadas: {resumen['total']}\n"
            f"OK: {resumen['ok']}   |   NOK: {resumen['nok']}   |   {pct_ok:.1f}% OK\n"
            f"Configuraciones de tolerancia encontradas: {resumen['configs']}"
            f"{extra}"
        ))
        self.result_frame.pack(fill="x", pady=(4, 0))

        try:
            os.startfile(resumen["output_path"])  # abre automaticamente al terminar
        except OSError:
            pass

    def _on_error(self, text: str):
        self.worker_running = False
        self.btn_select.config(state="normal")
        self.btn_generate.config(state="normal")
        self.progress["value"] = 0
        self.lbl_status.config(text="")
        messagebox.showerror(APP_TITLE, text)

    def on_open_excel(self):
        if self.output_path and os.path.exists(self.output_path):
            os.startfile(self.output_path)

    def on_open_folder(self):
        if self.output_path and os.path.exists(self.output_path):
            os.startfile(os.path.dirname(self.output_path))


def main():
    try:
        import ctypes
        ctypes.windll.shcore.SetProcessDpiAwareness(1)
    except Exception:
        pass

    app = App()
    app.mainloop()


if __name__ == "__main__":
    main()
