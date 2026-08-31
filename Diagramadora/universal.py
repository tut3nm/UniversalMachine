"""
Conversor UNIVERSAL de archivos de ensayo a Excel (prototipo con IA local).

A diferencia de "Amortiguadores_a_Excel", este programa no tiene ningun formato
programado de antemano: descubre la estructura del archivo por su cuenta y usa
un modelo de IA que corre DENTRO de la maquina (sin internet ni API keys) para
ponerle nombre a cada campo, leyendo el archivo con anotaciones del tecnico.
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

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "ai"))

import structure          # noqa: E402
import labeler            # noqa: E402
import generic_excel      # noqa: E402
import llm                # noqa: E402

APP_TITLE = "Conversor Universal de Ensayos a Excel  (prototipo con IA local)"


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
        self.geometry("860x680")
        self.minsize(780, 620)
        self.configure(bg="#F2F2F2")

        self.data_file: str | None = None
        self.annot_file: str | None = None
        self.output_path: str | None = None
        self.msg_queue: queue.Queue = queue.Queue()
        self.worker_running = False
        self.use_ai = tk.BooleanVar(value=True)

        self._build_ui()
        self.after(100, self._poll_queue)

    # ------------------------------------------------------------------
    def _build_ui(self):
        F_TITLE = ("Segoe UI", 15, "bold")
        F_TEXT = ("Segoe UI", 10)
        F_TEXT_B = ("Segoe UI", 10, "bold")
        F_BTN = ("Segoe UI", 11, "bold")
        F_SMALL = ("Segoe UI", 9)
        self.F_TEXT = F_TEXT
        self.F_TEXT_B = F_TEXT_B

        header = tk.Frame(self, bg="#1F4E78")
        header.pack(fill="x")
        tk.Label(header, text="Conversor Universal de Ensayos a Excel", font=F_TITLE,
                 bg="#1F4E78", fg="white", pady=10).pack(padx=20, anchor="w")
        tk.Label(header, text="Prototipo: descubre el formato solo y usa IA local (sin internet)",
                 font=F_SMALL, bg="#1F4E78", fg="#BDD7EE").pack(padx=20, anchor="w", pady=(0, 10))

        body = tk.Frame(self, bg="#F2F2F2")
        body.pack(fill="both", expand=True, padx=22, pady=14)

        # ---- estado de la IA
        ok, msg = llm.is_available()
        ai_frame = tk.Frame(body, bg="#E2EFDA" if ok else "#FFF2CC",
                            highlightbackground="#A9D08E" if ok else "#FFD966",
                            highlightthickness=1)
        ai_frame.pack(fill="x", pady=(0, 12))
        tk.Label(ai_frame,
                 text=("IA local: " + msg) if ok else ("IA local no disponible. " + msg),
                 font=F_TEXT, bg="#E2EFDA" if ok else "#FFF2CC",
                 fg="#375623" if ok else "#7F6000", anchor="w", justify="left",
                 wraplength=780).pack(fill="x", padx=12, pady=8)

        # ---- paso 1
        s1 = tk.LabelFrame(body, text=" Paso 1 - Archivo con los datos (obligatorio) ",
                           font=F_TEXT_B, bg="#F2F2F2", fg="#1F4E78", padx=12, pady=10)
        s1.pack(fill="x", pady=(0, 10))
        tk.Button(s1, text="Seleccionar archivo de datos...", font=F_BTN, bg="#1F4E78",
                  fg="white", relief="flat", padx=14, pady=8, cursor="hand2",
                  activebackground="#163A5C", activeforeground="white",
                  command=self.on_pick_data).pack(side="left")
        self.lbl_data = tk.Label(s1, text="Ninguno", font=F_TEXT, bg="#F2F2F2",
                                 fg="#666666", anchor="w")
        self.lbl_data.pack(side="left", padx=(14, 0), fill="x", expand=True)

        # ---- paso 2
        s2 = tk.LabelFrame(body, text=" Paso 2 - Archivo con anotaciones (opcional) ",
                           font=F_TEXT_B, bg="#F2F2F2", fg="#1F4E78", padx=12, pady=10)
        s2.pack(fill="x", pady=(0, 10))
        tk.Button(s2, text="Seleccionar anotaciones...", font=F_BTN, bg="#5A6B7B",
                  fg="white", relief="flat", padx=14, pady=8, cursor="hand2",
                  activebackground="#42505C", activeforeground="white",
                  command=self.on_pick_annot).pack(side="left")
        self.lbl_annot = tk.Label(s2, text="Ninguno", font=F_TEXT, bg="#F2F2F2",
                                  fg="#666666", anchor="w")
        self.lbl_annot.pack(side="left", padx=(14, 0), fill="x", expand=True)
        tk.Label(s2, text=(
            "Si el archivo de datos ya trae parametros con nombres claros (ej. CSV con "
            "PRESION_NOMINAL_BAR), este paso se puede saltear: la IA prolija esos nombres "
            "sola. Las anotaciones sirven cuando el equipo usa siglas (ej. E, C, CPEXTSUP)."
        ), font=F_SMALL, bg="#F2F2F2", fg="#888888", anchor="w", justify="left",
                 wraplength=780).pack(fill="x", pady=(6, 0))

        tk.Checkbutton(body, text="Usar la IA local para nombrar los campos "
                                  "(si se desmarca, es mucho mas rapido y usa los nombres del equipo)",
                       variable=self.use_ai, font=F_SMALL, bg="#F2F2F2",
                       fg="#333333", activebackground="#F2F2F2",
                       anchor="w").pack(fill="x", pady=(0, 10))

        # ---- paso 3
        s3 = tk.LabelFrame(body, text=" Paso 3 ", font=F_TEXT_B, bg="#F2F2F2",
                           fg="#1F4E78", padx=12, pady=10)
        s3.pack(fill="x", pady=(0, 10))
        self.btn_go = tk.Button(s3, text="Generar Excel", font=F_BTN, bg="#2E7D32",
                                fg="white", relief="flat", padx=16, pady=9, cursor="hand2",
                                activebackground="#1B5E20", activeforeground="white",
                                state="disabled", command=self.on_generate)
        self.btn_go.pack(side="left")
        self.progress = ttk.Progressbar(s3, orient="horizontal", mode="determinate", maximum=100)
        self.progress.pack(side="left", fill="x", expand=True, padx=(14, 0))

        self.lbl_status = tk.Label(body, text="", font=F_TEXT, bg="#F2F2F2",
                                   fg="#333333", anchor="w", justify="left", wraplength=800)
        self.lbl_status.pack(fill="x", pady=(2, 8))

        self.result_frame = tk.Frame(body, bg="#FFFFFF", highlightbackground="#CCCCCC",
                                     highlightthickness=1)
        self.result_text = tk.Label(self.result_frame, text="", font=F_TEXT, bg="#FFFFFF",
                                    fg="#333333", justify="left", anchor="w", wraplength=760)
        self.result_text.pack(fill="x", padx=14, pady=(14, 8))
        btns = tk.Frame(self.result_frame, bg="#FFFFFF")
        btns.pack(fill="x", padx=14, pady=(0, 14))
        tk.Button(btns, text="Abrir Excel", font=F_TEXT_B, bg="#1F4E78", fg="white",
                  relief="flat", padx=12, pady=6, cursor="hand2",
                  command=self.on_open_excel).pack(side="left")
        tk.Button(btns, text="Abrir carpeta", font=F_TEXT_B, bg="#5A6B7B", fg="white",
                  relief="flat", padx=12, pady=6, cursor="hand2",
                  command=self.on_open_folder).pack(side="left", padx=(10, 0))

    # ------------------------------------------------------------------
    def _pick(self, title):
        initial = os.path.join(os.path.expanduser("~"), "Desktop")
        if not os.path.isdir(initial):
            initial = os.path.expanduser("~")
        return filedialog.askopenfilename(
            title=title, initialdir=initial,
            filetypes=[("Archivos de texto", "*.txt"), ("Todos los archivos", "*.*")])

    def on_pick_data(self):
        p = self._pick("Archivo con los datos del ensayo")
        if not p:
            return
        self.data_file = p
        self.lbl_data.config(text=os.path.basename(p), fg="#1F4E78", font=self.F_TEXT_B)
        self.btn_go.config(state="normal")
        self.result_frame.pack_forget()

    def on_pick_annot(self):
        p = self._pick("Archivo con anotaciones (el que explica cada valor)")
        if not p:
            return
        self.annot_file = p
        self.lbl_annot.config(text=os.path.basename(p), fg="#1F4E78", font=self.F_TEXT_B)

    def on_generate(self):
        if not self.data_file or self.worker_running:
            return
        self.worker_running = True
        self.btn_go.config(state="disabled")
        self.result_frame.pack_forget()
        self.progress["value"] = 0
        self.lbl_status.config(text="Leyendo el archivo...")
        threading.Thread(target=self._worker, daemon=True).start()

    def _worker(self):
        try:
            lines = structure.read_text_file(self.data_file)

            def disc_progress(cur, total):
                self.msg_queue.put(("progress", (cur / total) * 25 if total else 0,
                                    "Descubriendo la estructura del archivo..."))

            disc = structure.discover(lines, progress_callback=disc_progress)

            if not disc.records:
                self.msg_queue.put(("error", (
                    "No se encontraron mediciones que se repitan en este archivo.\n\n"
                    "El programa busca un patron de lineas que se repita. Si el archivo "
                    "tiene otro tipo de estructura, este prototipo todavia no lo cubre.")))
                return

            annotated_text = None
            if self.annot_file:
                annotated_text = "".join(structure.read_text_file(self.annot_file))

            def lab_progress(texto, secs):
                self.msg_queue.put(("progress", 30,
                                    f"{texto}  (IA local trabajando: {secs:.0f}s)"))

            self.msg_queue.put(("progress", 28, "Preparando la IA local..."))
            labels = labeler.build_labels(
                disc, annotated_text,
                use_ai=self.use_ai.get(),
                progress_callback=lab_progress,
            )

            out = default_output_path(self.data_file)

            def xls_progress(cur, total):
                self.msg_queue.put(("progress", 55 + (cur / total) * 45 if total else 55,
                                    "Generando el Excel..."))

            generic_excel.write_excel(disc, labels, out, self.data_file,
                                      annotated_path=self.annot_file,
                                      progress_callback=xls_progress)

            self.msg_queue.put(("done", {
                "out": out,
                "records": len(disc.records),
                "fields": len(disc.record_field_names),
                "configs": len(disc.config_snapshots),
                "period": disc.period,
                "unparsed": len(disc.unparsed_lines),
                "messages": labels.messages,
                "used_ai": labels.used_ai,
            }))
        except Exception as exc:  # noqa: BLE001
            p = log_error(exc)
            self.msg_queue.put(("error",
                                f"Ocurrio un error inesperado.\n\nDetalle tecnico en:\n{p}"))

    def _poll_queue(self):
        try:
            while True:
                msg = self.msg_queue.get_nowait()
                if msg[0] == "progress":
                    self.progress["value"] = msg[1]
                    self.lbl_status.config(text=msg[2])
                elif msg[0] == "done":
                    self._done(msg[1])
                elif msg[0] == "error":
                    self._error(msg[1])
        except queue.Empty:
            pass
        self.after(100, self._poll_queue)

    def _done(self, r):
        self.worker_running = False
        self.btn_go.config(state="normal")
        self.progress["value"] = 100
        self.lbl_status.config(text="Listo.")
        self.output_path = r["out"]
        extra = "\n".join("  - " + m for m in r["messages"])
        self.result_text.config(text=(
            f"Excel generado:\n{r['out']}\n\n"
            f"Mediciones: {r['records']}    Campos por medicion: {r['fields']}\n"
            f"Bloques de configuracion: {r['configs']}    "
            f"Lineas por medicion: {r['period']}\n"
            f"Lineas no interpretadas: {r['unparsed']}\n\n"
            f"{extra}"
        ))
        self.result_frame.pack(fill="x")
        try:
            os.startfile(r["out"])
        except OSError:
            pass

    def _error(self, text):
        self.worker_running = False
        self.btn_go.config(state="normal")
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
    App().mainloop()


if __name__ == "__main__":
    main()
