"""
Editor de recetas de maquina (formato CSV parametro x producto).

Dos pasos, en dos direcciones:
  1) A partir del CSV de la maquina -> genera un Excel editable.
  2) A partir de ese Excel YA EDITADO + el CSV ORIGINAL -> genera un CSV
     actualizado, cambiando SOLO las celdas que efectivamente cambiaron, y
     mostrando un listado completo de los cambios antes de guardar.

Pensado para archivos de "puesta a punto" que la maquina despues LEE para
configurarse: por eso nunca se sobreescribe el original, siempre se pide
revisar el listado de cambios, y se hace una auto-verificacion releyendo el
archivo generado antes de darlo por bueno.
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
import csv_recipe as R  # noqa: E402

APP_TITLE = "Editor de Recetas de Máquina (CSV de puesta a punto)"


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


def next_free_path(folder: str, name: str, ext: str) -> str:
    candidate = os.path.join(folder, f"{name}{ext}")
    n = 2
    while os.path.exists(candidate):
        candidate = os.path.join(folder, f"{name} ({n}){ext}")
        n += 1
    return candidate


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title(APP_TITLE)
        self.geometry("880x720")
        self.minsize(800, 640)
        self.configure(bg="#F2F2F2")

        self.csv_path: str | None = None
        self.xlsx_out: str | None = None
        self.edited_xlsx_path: str | None = None
        self.original_for_reverse: str | None = None
        self.msg_queue: queue.Queue = queue.Queue()
        self.busy = False

        self._build_ui()
        self.after(100, self._poll_queue)

    # ------------------------------------------------------------------
    def _build_ui(self):
        F_TITLE = ("Segoe UI", 15, "bold")
        F_SEC = ("Segoe UI", 11, "bold")
        F_TEXT = ("Segoe UI", 10)
        F_BTN = ("Segoe UI", 11, "bold")
        F_SMALL = ("Segoe UI", 9)
        self.F_TEXT = F_TEXT

        header = tk.Frame(self, bg="#1F4E78")
        header.pack(fill="x")
        tk.Label(header, text=APP_TITLE, font=F_TITLE, bg="#1F4E78", fg="white",
                 pady=10).pack(padx=20, anchor="w")

        warn = tk.Frame(self, bg="#FFF2CC", highlightbackground="#FFD966", highlightthickness=1)
        warn.pack(fill="x")
        tk.Label(warn, text=(
            "Este archivo se usa para configurar una máquina. Nunca se sobreescribe el "
            "original: siempre se genera un archivo nuevo, y se muestra el listado completo "
            "de cambios para revisar antes de usarlo en el equipo."
        ), font=F_TEXT, bg="#FFF2CC", fg="#7F6000", wraplength=840, justify="left").pack(
            padx=14, pady=8, anchor="w")

        nb = ttk.Notebook(self)
        nb.pack(fill="both", expand=True, padx=16, pady=12)

        tab1 = tk.Frame(nb, bg="#F2F2F2")
        tab2 = tk.Frame(nb, bg="#F2F2F2")
        nb.add(tab1, text="  1. Generar Excel editable  ")
        nb.add(tab2, text="  2. Aplicar cambios al original  ")

        # ---- TAB 1 ----------------------------------------------------
        s1 = tk.LabelFrame(tab1, text=" Archivo CSV de la máquina ", font=F_SEC,
                           bg="#F2F2F2", fg="#1F4E78", padx=14, pady=12)
        s1.pack(fill="x", padx=6, pady=10)
        tk.Button(s1, text="Seleccionar archivo .csv...", font=F_BTN, bg="#1F4E78",
                  fg="white", relief="flat", padx=14, pady=8, cursor="hand2",
                  command=self.on_pick_csv).pack(side="left")
        self.lbl_csv = tk.Label(s1, text="Ninguno", font=F_TEXT, bg="#F2F2F2",
                                fg="#666666", anchor="w")
        self.lbl_csv.pack(side="left", padx=(14, 0), fill="x", expand=True)

        self.lbl_csv_info = tk.Label(tab1, text="", font=F_TEXT, bg="#F2F2F2",
                                     fg="#333333", justify="left", anchor="w", wraplength=820)
        self.lbl_csv_info.pack(fill="x", padx=6, pady=(0, 10))

        self.btn_export = tk.Button(tab1, text="Generar Excel editable", font=F_BTN,
                                    bg="#2E7D32", fg="white", relief="flat", padx=16, pady=9,
                                    cursor="hand2", state="disabled", command=self.on_export)
        self.btn_export.pack(padx=6, anchor="w")

        self.progress1 = ttk.Progressbar(tab1, orient="horizontal", mode="indeterminate")
        self.progress1.pack(fill="x", padx=6, pady=8)

        self.result1 = tk.Frame(tab1, bg="#FFFFFF", highlightbackground="#CCCCCC", highlightthickness=1)
        self.result1_text = tk.Label(self.result1, text="", font=F_TEXT, bg="#FFFFFF",
                                     fg="#333333", justify="left", anchor="w", wraplength=800)
        self.result1_text.pack(fill="x", padx=14, pady=12)
        tk.Button(self.result1, text="Abrir Excel", font=F_BTN, bg="#1F4E78", fg="white",
                  relief="flat", padx=12, pady=6, cursor="hand2",
                  command=self.on_open_export).pack(padx=14, pady=(0, 12), anchor="w")

        # ---- TAB 2 ----------------------------------------------------
        s2 = tk.LabelFrame(tab2, text=" Paso A - Excel ya editado ", font=F_SEC,
                           bg="#F2F2F2", fg="#1F4E78", padx=14, pady=12)
        s2.pack(fill="x", padx=6, pady=10)
        tk.Button(s2, text="Seleccionar Excel editado...", font=F_BTN, bg="#1F4E78",
                  fg="white", relief="flat", padx=14, pady=8, cursor="hand2",
                  command=self.on_pick_edited).pack(side="left")
        self.lbl_edited = tk.Label(s2, text="Ninguno", font=F_TEXT, bg="#F2F2F2",
                                   fg="#666666", anchor="w")
        self.lbl_edited.pack(side="left", padx=(14, 0), fill="x", expand=True)

        s3 = tk.LabelFrame(tab2, text=" Paso B - Archivo .csv ORIGINAL (el mismo que se usó en el Paso 1) ",
                           font=F_SEC, bg="#F2F2F2", fg="#1F4E78", padx=14, pady=12)
        s3.pack(fill="x", padx=6, pady=10)
        tk.Button(s3, text="Seleccionar CSV original...", font=F_BTN, bg="#5A6B7B",
                  fg="white", relief="flat", padx=14, pady=8, cursor="hand2",
                  command=self.on_pick_original).pack(side="left")
        self.lbl_original = tk.Label(s3, text="Ninguno", font=F_TEXT, bg="#F2F2F2",
                                     fg="#666666", anchor="w")
        self.lbl_original.pack(side="left", padx=(14, 0), fill="x", expand=True)

        self.btn_apply = tk.Button(tab2, text="Comparar y generar CSV actualizado", font=F_BTN,
                                   bg="#2E7D32", fg="white", relief="flat", padx=16, pady=9,
                                   cursor="hand2", state="disabled", command=self.on_apply)
        self.btn_apply.pack(padx=6, pady=(4, 0), anchor="w")

        self.progress2 = ttk.Progressbar(tab2, orient="horizontal", mode="indeterminate")
        self.progress2.pack(fill="x", padx=6, pady=8)

        tk.Label(tab2, text="Cambios detectados:", font=F_SEC, bg="#F2F2F2",
                 fg="#1F4E78").pack(padx=6, anchor="w")
        list_frame = tk.Frame(tab2, bg="#F2F2F2")
        list_frame.pack(fill="both", expand=True, padx=6, pady=(4, 8))
        cols = ("parametro", "producto", "antes", "despues")
        self.tree = ttk.Treeview(list_frame, columns=cols, show="headings", height=10)
        for c, label, w in (("parametro", "Parámetro", 260), ("producto", "Producto", 160),
                            ("antes", "Antes", 100), ("despues", "Después", 100)):
            self.tree.heading(c, text=label)
            self.tree.column(c, width=w, anchor="w")
        vsb = ttk.Scrollbar(list_frame, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=vsb.set)
        self.tree.pack(side="left", fill="both", expand=True)
        vsb.pack(side="right", fill="y")

        self.lbl_warnings = tk.Label(tab2, text="", font=F_TEXT, bg="#FFF2CC",
                                     fg="#7F6000", justify="left", anchor="w", wraplength=820)

        self.result2 = tk.Frame(tab2, bg="#FFFFFF", highlightbackground="#CCCCCC", highlightthickness=1)
        self.result2_text = tk.Label(self.result2, text="", font=F_TEXT, bg="#FFFFFF",
                                     fg="#333333", justify="left", anchor="w", wraplength=800)
        self.result2_text.pack(fill="x", padx=14, pady=12)
        btns2 = tk.Frame(self.result2, bg="#FFFFFF")
        btns2.pack(padx=14, pady=(0, 12), anchor="w")
        tk.Button(btns2, text="Abrir carpeta", font=F_BTN, bg="#5A6B7B", fg="white",
                  relief="flat", padx=12, pady=6, cursor="hand2",
                  command=self.on_open_result_folder).pack(side="left")

    # ------------------------------------------------------------------
    def _pick_file(self, title, types):
        initial = os.path.join(os.path.expanduser("~"), "Desktop")
        if not os.path.isdir(initial):
            initial = os.path.expanduser("~")
        return filedialog.askopenfilename(title=title, initialdir=initial, filetypes=types)

    def on_pick_csv(self):
        p = self._pick_file("Archivo CSV de la máquina",
                            [("CSV", "*.csv"), ("Todos los archivos", "*.*")])
        if not p:
            return
        self.csv_path = p
        self.lbl_csv.config(text=os.path.basename(p), fg="#1F4E78", font=("Segoe UI", 10, "bold"))
        ok, msg = R.sniff(p)
        self.lbl_csv_info.config(
            text=(f"{msg}" if ok else f"Advertencia: {msg} (se puede intentar igual)"),
            fg="#333333" if ok else "#C00000")
        self.btn_export.config(state="normal")
        self.result1.pack_forget()

    def on_export(self):
        if not self.csv_path or self.busy:
            return
        self.busy = True
        self.btn_export.config(state="disabled")
        self.progress1.start(12)
        threading.Thread(target=self._worker_export, daemon=True).start()

    def _worker_export(self):
        try:
            rec = R.read_recipe(self.csv_path)
            folder = os.path.dirname(self.csv_path)
            name = os.path.splitext(os.path.basename(self.csv_path))[0]
            out = next_free_path(folder, f"{name} (editable)", ".xlsx")
            R.write_excel_recipe(rec, out, self.csv_path)
            self.msg_queue.put(("export_done", {
                "out": out, "n_params": len(rec.params), "n_products": len(rec.product_codes),
            }))
        except Exception as exc:  # noqa: BLE001
            p = log_error(exc)
            self.msg_queue.put(("export_error", f"No se pudo generar el Excel.\n\nDetalle: {exc}\n\nLog: {p}"))

    def on_open_export(self):
        if self.xlsx_out and os.path.exists(self.xlsx_out):
            os.startfile(self.xlsx_out)

    # ---- Tab 2 ----------------------------------------------------------
    def on_pick_edited(self):
        p = self._pick_file("Excel ya editado", [("Excel", "*.xlsx"), ("Todos", "*.*")])
        if not p:
            return
        self.edited_xlsx_path = p
        self.lbl_edited.config(text=os.path.basename(p), fg="#1F4E78", font=("Segoe UI", 10, "bold"))
        self._maybe_enable_apply()

    def on_pick_original(self):
        p = self._pick_file("Archivo CSV original", [("CSV", "*.csv"), ("Todos", "*.*")])
        if not p:
            return
        self.original_for_reverse = p
        self.lbl_original.config(text=os.path.basename(p), fg="#1F4E78", font=("Segoe UI", 10, "bold"))
        self._maybe_enable_apply()

    def _maybe_enable_apply(self):
        if self.edited_xlsx_path and self.original_for_reverse:
            self.btn_apply.config(state="normal")

    def on_apply(self):
        if self.busy:
            return
        self.busy = True
        self.btn_apply.config(state="disabled")
        self.progress2.start(12)
        for row in self.tree.get_children():
            self.tree.delete(row)
        self.lbl_warnings.pack_forget()
        self.result2.pack_forget()
        threading.Thread(target=self._worker_apply, daemon=True).start()

    def _worker_apply(self):
        try:
            rec = R.read_recipe(self.original_for_reverse)
            edited = R.read_edited_excel(self.edited_xlsx_path)
            folder = os.path.dirname(self.original_for_reverse)
            name = os.path.splitext(os.path.basename(self.original_for_reverse))[0]
            out = next_free_path(folder, f"{name} (actualizado)", ".csv")
            res = R.rebuild_csv(self.original_for_reverse, rec, edited, out)
            self.msg_queue.put(("apply_done", res))
        except Exception as exc:  # noqa: BLE001
            p = log_error(exc)
            self.msg_queue.put(("apply_error",
                f"No se pudo comparar/generar el archivo.\n\nDetalle: {exc}\n\nLog: {p}"))

    def on_open_result_folder(self):
        if self.original_for_reverse:
            os.startfile(os.path.dirname(self.original_for_reverse))

    # ------------------------------------------------------------------
    def _poll_queue(self):
        try:
            while True:
                kind, payload = self.msg_queue.get_nowait()
                if kind == "export_done":
                    self._export_done(payload)
                elif kind == "export_error":
                    self._export_error(payload)
                elif kind == "apply_done":
                    self._apply_done(payload)
                elif kind == "apply_error":
                    self._apply_error(payload)
        except queue.Empty:
            pass
        self.after(100, self._poll_queue)

    def _export_done(self, r):
        self.busy = False
        self.btn_export.config(state="normal")
        self.progress1.stop()
        self.xlsx_out = r["out"]
        self.result1_text.config(text=(
            f"Excel generado:\n{r['out']}\n\n"
            f"{r['n_products']} productos × {r['n_params']} parámetros.\n\n"
            "Editá los valores que necesites en la hoja 'Recetas' y guardá el archivo. "
            "Después usá la pestaña '2. Aplicar cambios al original' con este Excel y "
            "el mismo .csv que usaste acá."
        ))
        self.result1.pack(fill="x", padx=6, pady=6)
        try:
            os.startfile(r["out"])
        except OSError:
            pass

    def _export_error(self, text):
        self.busy = False
        self.btn_export.config(state="normal")
        self.progress1.stop()
        messagebox.showerror(APP_TITLE, text)

    def _apply_done(self, res: R.ReverseResult):
        self.busy = False
        self.btn_apply.config(state="normal")
        self.progress2.stop()

        for ch in res.changes:
            self.tree.insert("", "end", values=(ch.parametro, ch.producto, ch.valor_anterior, ch.valor_nuevo))

        if res.warnings:
            self.lbl_warnings.config(text="ATENCIÓN:\n" + "\n".join(f"• {w}" for w in res.warnings))
            self.lbl_warnings.pack(fill="x", padx=6, pady=(0, 8))

        if not res.ok:
            self.result2_text.config(text=(
                "El programa detectó una inconsistencia grave al reverificar el archivo "
                f"generado ({res.output_path}). NO USAR este archivo en la máquina sin "
                "revisar manualmente. Ver el detalle en rojo arriba."
            ))
        elif res.changes:
            self.result2_text.config(text=(
                f"Archivo generado: {res.output_path}\n\n"
                f"{len(res.changes)} cambio(s) aplicado(s), listados arriba. Todo lo demás del "
                "archivo original quedó exactamente igual.\n\n"
                "Revisar la lista de cambios antes de usar este archivo en la máquina."
            ))
        else:
            self.result2_text.config(text=(
                "No se detectó ningún cambio entre el Excel y el archivo original: "
                "el archivo generado es idéntico al original. No hace falta cargarlo de nuevo."
            ))
        self.result2.pack(fill="x", padx=6, pady=6)

    def _apply_error(self, text):
        self.busy = False
        self.btn_apply.config(state="normal")
        self.progress2.stop()
        messagebox.showerror(APP_TITLE, text)


def main():
    try:
        import ctypes
        ctypes.windll.shcore.SetProcessDpiAwareness(1)
    except Exception:
        pass
    App().mainloop()


if __name__ == "__main__":
    main()
