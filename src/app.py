"""
app.py — Configurador Máquina 232
=================================
Interfaz de escritorio (Tkinter) para editar el archivo de recetas de la
máquina 232.

Funciones:
  * Buscar piezas por código.
  * Crear / modificar / eliminar registros.
  * Guardado automático en datos232/actual.csv (formato idéntico al original).
  * Exportar el CSV actual o el original a cualquier carpeta de la PC.
  * Restaurar el archivo original.

El original de fábrica queda embebido y se copia una sola vez a
datos232/original.csv, que la aplicación nunca modifica.
"""

from __future__ import annotations

import os
import shutil
import sys
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

# Permite ejecutar tanto `python src/app.py` como el módulo empaquetado.
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from recipe_store import (  # noqa: E402
    COLOR_LABEL,
    GRAMS_LABEL,
    SPEED_LABEL,
    Recipe,
    RecipeStore,
    app_data_dir,
    code_signature,
    resource_path,
)
try:
    import excel_import  # noqa: E402
except ImportError:
    # Falta openpyxl: el resto de la app funciona igual, solo se deshabilita
    # "Importar cambios" (ver App.on_import).
    excel_import = None

APP_TITLE = "Configurador Máquina 232"
FACTORY_CSV = "recetas232.csv"

# --- Paleta: blanco, grises y verde hoja -------------------------------------
WHITE = "#FFFFFF"
BG = "#F4F6F3"
PANEL = "#FFFFFF"
BORDER = "#D7DCD5"
TEXT = "#2B2F2B"
MUTED = "#727A71"
GREEN = "#4E9A51"          # verde hoja principal
GREEN_DARK = "#3C7A3F"
GREEN_DEEP = "#2F5F31"
GREEN_LIGHT = "#E7F1E3"    # fondo de selección / acentos suaves
RED = "#B4472E"
RED_DARK = "#8F3623"
GREY_BTN = "#EDEFEC"
GREY_BTN_HOVER = "#E1E4DF"

FONT = ("Segoe UI", 10)
FONT_BOLD = ("Segoe UI", 10, "bold")
FONT_TITLE = ("Segoe UI Semibold", 15)
FONT_SMALL = ("Segoe UI", 9)


def enable_dpi_awareness() -> None:
    """Texto nítido en pantallas de alta densidad (Windows)."""
    try:
        from ctypes import windll
        windll.shcore.SetProcessDpiAwareness(1)
    except Exception:
        pass


class FlatButton(tk.Button):
    """Botón plano con estados de hover, en 4 estilos."""

    STYLES = {
        "primary": (GREEN, WHITE, GREEN_DARK),
        "danger": (RED, WHITE, RED_DARK),
        "secondary": (GREY_BTN, TEXT, GREY_BTN_HOVER),
        "ghost": (WHITE, GREEN_DARK, GREEN_LIGHT),
    }

    def __init__(self, parent, text, command=None, kind="secondary",
                small=False, **kw):
        bg, fg, hover = self.STYLES[kind]
        self._bg, self._hover = bg, hover
        opts = dict(
            bg=bg, fg=fg, activebackground=hover, activeforeground=fg,
            font=(FONT_SMALL if small else FONT_BOLD), relief="flat", bd=0,
            padx=(9 if small else 16), pady=(3 if small else 8), cursor="hand2",
            highlightthickness=1, highlightbackground=BORDER,
            highlightcolor=BORDER,
        )
        opts.update(kw)
        super().__init__(parent, text=text, command=command, **opts)
        self.bind("<Enter>", lambda e: self.config(bg=self._hover))
        self.bind("<Leave>", lambda e: self.config(bg=self._bg))


class RecipeDialog(tk.Toplevel):
    """Diálogo modal para crear o editar un registro."""

    def __init__(self, parent, store: RecipeStore, title: str,
                 recipe: Recipe | None = None, edit_index: int | None = None):
        super().__init__(parent)
        self.store = store
        self.edit_index = edit_index
        self.result: Recipe | None = None

        self.title(title)
        self.configure(bg=PANEL)
        self.resizable(False, False)
        self.transient(parent)

        self.var_code = tk.StringVar(value=recipe.code if recipe else "")
        self.var_color = tk.StringVar(value=str(recipe.color) if recipe else "1")
        self.var_grams = tk.StringVar(value=str(recipe.grams) if recipe else "0")
        self.var_speed = tk.StringVar(value=str(recipe.speed) if recipe else "350")

        self._build(title)
        self._center_on(parent)

        self.grab_set()
        self.entry_code.focus_set()
        self.bind("<Return>", lambda e: self._on_ok())
        self.bind("<Escape>", lambda e: self.destroy())
        self.after(50, self._center_on, parent)
        self.wait_window(self)

    def _build(self, title: str) -> None:
        header = tk.Frame(self, bg=GREEN, height=52)
        header.pack(fill="x")
        header.pack_propagate(False)
        tk.Label(header, text=title, bg=GREEN, fg=WHITE,
                 font=("Segoe UI Semibold", 13)).pack(side="left", padx=18)

        body = tk.Frame(self, bg=PANEL, padx=24, pady=20)
        body.pack(fill="both", expand=True)

        self.entry_code = self._field(body, 0, "Código de la pieza", self.var_code)
        self._field(body, 1, "Color", self.var_color, hint="1 a 3", spin=(1, 9))
        self._field(body, 2, GRAMS_LABEL.split("_")[-1], self.var_grams,
                    hint="gramos de carga (aceite)")
        self._field(body, 3, SPEED_LABEL.split("_")[-1], self.var_speed,
                    hint="velocidad de inicio")

        footer = tk.Frame(self, bg=PANEL, padx=24)
        footer.pack(fill="x", pady=(0, 20))
        FlatButton(footer, "Cancelar", self.destroy, kind="secondary").pack(side="right")
        FlatButton(footer, "Guardar", self._on_ok, kind="primary").pack(
            side="right", padx=(0, 10))

    def _field(self, parent, row, label, var, hint="", spin=None):
        tk.Label(parent, text=label, bg=PANEL, fg=TEXT, font=FONT_BOLD,
                 anchor="w").grid(row=row * 2, column=0, sticky="w", pady=(8, 2))
        if spin:
            widget = tk.Spinbox(parent, from_=spin[0], to=spin[1], textvariable=var,
                                font=FONT, width=30, relief="solid", bd=1,
                                highlightthickness=1, highlightbackground=BORDER,
                                highlightcolor=GREEN, buttonbackground=GREY_BTN)
        else:
            widget = tk.Entry(parent, textvariable=var, font=FONT, width=32,
                              relief="solid", bd=1, highlightthickness=1,
                              highlightbackground=BORDER, highlightcolor=GREEN)
        widget.grid(row=row * 2 + 1, column=0, sticky="we", ipady=4)
        if hint:
            tk.Label(parent, text=hint, bg=PANEL, fg=MUTED, font=FONT_SMALL,
                     anchor="w").grid(row=row * 2 + 1, column=1, sticky="w", padx=(10, 0))
        parent.columnconfigure(0, weight=1)
        return widget

    def _center_on(self, parent) -> None:
        self.update_idletasks()
        w, h = self.winfo_reqwidth(), self.winfo_reqheight()
        px, py = parent.winfo_rootx(), parent.winfo_rooty()
        pw, ph = parent.winfo_width(), parent.winfo_height()
        x = px + (pw - w) // 2
        y = py + (ph - h) // 3
        self.geometry(f"+{max(x, 0)}+{max(y, 0)}")

    def _on_ok(self) -> None:
        code = self.var_code.get().strip()
        if not code:
            messagebox.showwarning("Dato faltante",
                                   "El código de la pieza no puede estar vacío.",
                                   parent=self)
            return
        dup = self.store.find_code(code, exclude_index=self.edit_index)
        if dup != -1:
            messagebox.showwarning(
                "Código duplicado",
                f"Ya existe un registro con el código «{code}» "
                f"(posición {dup + 1}).", parent=self)
            return
        try:
            color = int(self.var_color.get())
            grams = int(self.var_grams.get())
            speed = int(self.var_speed.get())
        except ValueError:
            messagebox.showwarning(
                "Valor inválido",
                "Color, Gramos y Velocidad deben ser números enteros.",
                parent=self)
            return
        if min(color, grams, speed) < 0:
            messagebox.showwarning("Valor inválido",
                                   "Los valores no pueden ser negativos.",
                                   parent=self)
            return
        self.result = Recipe(code=code, color=color, grams=grams, speed=speed)
        self.destroy()


def build_scrollable_canvas(dialog: tk.Toplevel, container: tk.Widget) -> tuple[tk.Canvas, tk.Frame]:
    """Crea un área con scroll vertical (rueda del mouse incluida) dentro de
    `container`. El binding de la rueda se hace con bind_all (para que
    funcione aunque el cursor esté sobre un widget hijo), y se desregistra
    automáticamente al destruirse `dialog` para no dejar callbacks colgados
    apuntando a un canvas ya destruido."""
    outer = tk.Frame(container, bg=PANEL)
    outer.pack(fill="both", expand=True)
    canvas = tk.Canvas(outer, bg=PANEL, highlightthickness=0)
    vsb = ttk.Scrollbar(outer, orient="vertical", command=canvas.yview)
    inner = tk.Frame(canvas, bg=PANEL)
    inner.bind("<Configure>",
               lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
    canvas.create_window((0, 0), window=inner, anchor="nw")
    canvas.configure(yscrollcommand=vsb.set)
    canvas.pack(side="left", fill="both", expand=True)
    vsb.pack(side="right", fill="y")

    def _on_wheel(event):
        canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")
    canvas.bind_all("<MouseWheel>", _on_wheel)

    def _unbind_wheel(event) -> None:
        if event.widget is dialog:
            canvas.unbind_all("<MouseWheel>")
    dialog.bind("<Destroy>", _unbind_wheel, add="+")

    return canvas, inner


class DuplicatesDialog(tk.Toplevel):
    """Muestra grupos de códigos posiblemente duplicados (mismo código
    ignorando ceros, p. ej. '00049810005962' y '004981005962') para que el
    usuario decida manualmente, con un check por registro, cuáles eliminar.
    """

    def __init__(self, parent, store: RecipeStore):
        super().__init__(parent)
        self.store = store
        self.deleted_any = False
        self.reviewed_any = False

        self.title("Posibles duplicados")
        self.configure(bg=PANEL)
        self.geometry("760x580")
        self.minsize(620, 380)
        self.transient(parent)

        self.groups = store.find_similar_groups()
        self._check_vars: dict[int, tk.BooleanVar] = {}
        self._row_widgets: dict[int, dict] = {}

        self._build()
        self.after(50, self._center_on, parent)

        self.grab_set()
        self.bind("<Escape>", lambda e: self.destroy())
        self.wait_window(self)

    def _build(self) -> None:
        header = tk.Frame(self, bg=GREEN, height=56)
        header.pack(fill="x")
        header.pack_propagate(False)
        tk.Label(header, text="Posibles duplicados", bg=GREEN, fg=WHITE,
                 font=("Segoe UI Semibold", 13)).pack(side="left", padx=18)

        n_groups = len(self.groups)
        n_records = sum(len(g) for g in self.groups)
        sub = tk.Label(
            self, bg=PANEL, fg=MUTED, font=FONT_SMALL, anchor="w", justify="left",
            text=(
                f"{n_groups} grupo(s) con {n_records} registro(s) cuyo código "
                "coincide al ignorar los dígitos '0'. Copiá el código para "
                "buscarlo en SAP; marcá \"Eliminar\" si es un duplicado real, "
                "o \"No es duplicado\" para descartarlo de esta búsqueda."
                if n_groups else
                "No se encontraron códigos con posible duplicado."
            ),
        )
        sub.pack(fill="x", padx=18, pady=(10, 6))

        # Área con scroll
        wrap = tk.Frame(self, bg=PANEL, padx=18)
        wrap.pack(fill="both", expand=True)
        canvas, inner = build_scrollable_canvas(self, wrap)

        for gi, group in enumerate(self.groups):
            card = tk.Frame(inner, bg=WHITE, highlightthickness=1,
                            highlightbackground=BORDER)
            card.pack(fill="x", pady=(0, 10), padx=(0, 14))
            tk.Label(card, text=f"Grupo {gi + 1}", bg=WHITE, fg=GREEN_DARK,
                     font=FONT_BOLD, anchor="w").pack(fill="x", padx=12, pady=(8, 2))
            for idx in group:
                self._build_row(card, idx)
            tk.Frame(card, bg=WHITE, height=6).pack()

        footer = tk.Frame(self, bg=PANEL, padx=18)
        footer.pack(fill="x", pady=14)
        FlatButton(footer, "Cerrar", self.destroy, kind="secondary").pack(side="right")
        FlatButton(footer, "Eliminar seleccionados", self._on_apply,
                  kind="danger").pack(side="right", padx=(0, 10))

    def _build_row(self, card: tk.Frame, idx: int) -> None:
        r = self.store.recipes[idx]
        var = tk.BooleanVar(value=False)
        self._check_vars[idx] = var
        row = tk.Frame(card, bg=WHITE)
        row.pack(fill="x", padx=12, pady=2)

        chk = tk.Checkbutton(
            row, variable=var, bg=WHITE, activebackground=WHITE,
            selectcolor=WHITE, bd=0, highlightthickness=0, cursor="hand2",
        )
        chk.pack(side="left")
        text = (f"{r.code}   ·   Color {r.color}   ·   "
                f"{r.grams} g   ·   Vel. {r.speed}")
        lbl = tk.Label(row, text=text, bg=WHITE, fg=TEXT, font=FONT, anchor="w")
        lbl.pack(side="left", fill="x", expand=True)

        keep_btn = FlatButton(row, "No es duplicado",
                              lambda i=idx: self._mark_not_duplicate(i),
                              kind="ghost", small=True)
        keep_btn.pack(side="right", padx=(6, 0))
        copy_btn = FlatButton(row, "Copiar código",
                              lambda c=r.code: self._copy_code(c),
                              kind="secondary", small=True)
        copy_btn.pack(side="right")

        self._row_widgets[idx] = {
            "row": row, "label": lbl, "checkbox": chk,
            "keep_btn": keep_btn, "copy_btn": copy_btn,
        }

    def _copy_code(self, code: str) -> None:
        self.clipboard_clear()
        self.clipboard_append(code)
        self._set_status_hint(f"Código «{code}» copiado al portapapeles.")

    def _mark_not_duplicate(self, idx: int) -> None:
        self.store.recipes[idx].not_duplicate = True
        self.reviewed_any = True
        widgets = self._row_widgets[idx]
        self._check_vars[idx].set(False)
        widgets["checkbox"].config(state="disabled")
        widgets["keep_btn"].config(state="disabled", text="Marcado: no es duplicado")
        widgets["copy_btn"].config(state="disabled")
        widgets["label"].config(fg=MUTED)
        self._set_status_hint(f"«{self.store.recipes[idx].code}» marcado como "
                              "no duplicado; no volverá a aparecer acá.")

    def _set_status_hint(self, text: str) -> None:
        if not hasattr(self, "_hint_label"):
            self._hint_label = tk.Label(self, bg=PANEL, fg=GREEN_DARK,
                                        font=FONT_SMALL, anchor="w")
            self._hint_label.pack(fill="x", padx=18, side="bottom", pady=(0, 4))
        self._hint_label.config(text=text)

    def _center_on(self, parent) -> None:
        self.update_idletasks()
        w, h = self.winfo_width(), self.winfo_height()
        px, py = parent.winfo_rootx(), parent.winfo_rooty()
        pw, ph = parent.winfo_width(), parent.winfo_height()
        x = px + (pw - w) // 2
        y = py + (ph - h) // 3
        self.geometry(f"+{max(x, 0)}+{max(y, 0)}")

    def _on_apply(self) -> None:
        selected = [i for i, v in self._check_vars.items() if v.get()]
        if not selected:
            messagebox.showinfo("Sin selección",
                                "No marcaste ningún registro para eliminar.",
                                parent=self)
            return
        codes = [self.store.recipes[i].code for i in selected]
        preview = ", ".join(codes[:6]) + (" …" if len(codes) > 6 else "")
        if not messagebox.askyesno(
                "Confirmar eliminación",
                f"¿Eliminar {len(selected)} registro(s) marcados como "
                f"duplicados?\n\n{preview}", parent=self):
            return
        for i in sorted(selected, reverse=True):
            self.store.delete(i)
        self.deleted_any = True
        self.destroy()


class ImportDialog(tk.Toplevel):
    """Asistente para "Importar cambios" desde un Excel de formato variable.

    Pasos:
      1. Elegir hoja (si el libro tiene más de una).
      2. Mapear qué columna del Excel corresponde a Código, Color, Gramos de
         Carga y Velocidad Inicio (con sugerencia automática por nombre).
      3. Revisar los registros que difieren del CSV actual y elegir cuáles
         aplicar; solo los marcados se modifican.
    """

    def __init__(self, parent, store: RecipeStore, workbook, filename: str):
        super().__init__(parent)
        self.store = store
        self.workbook = workbook
        self.filename = filename
        self.applied_any = False
        self.sheet: str | None = None
        self._headers: list[str] = []
        self._combo_vars: dict[str, tk.StringVar] = {}

        self.title(f"Importar cambios — {filename}")
        self.configure(bg=PANEL)
        self.geometry("700x600")
        self.minsize(580, 440)
        self.transient(parent)

        self._header_frame = tk.Frame(self, bg=GREEN, height=56)
        self._header_frame.pack(fill="x")
        self._header_frame.pack_propagate(False)
        self._header_label = tk.Label(
            self._header_frame, text="Importar cambios", bg=GREEN, fg=WHITE,
            font=("Segoe UI Semibold", 13))
        self._header_label.pack(side="left", padx=18)

        self._content = tk.Frame(self, bg=PANEL)
        self._content.pack(fill="both", expand=True)

        sheets = excel_import.sheet_names(workbook)
        if len(sheets) == 1:
            self.sheet = sheets[0]
            self._show_mapping_step()
        else:
            self._show_sheet_step(sheets)

        self.after(50, self._center_on, parent)
        self.grab_set()
        self.bind("<Escape>", lambda e: self.destroy())
        self.wait_window(self)

    def _center_on(self, parent) -> None:
        self.update_idletasks()
        w, h = self.winfo_width(), self.winfo_height()
        px, py = parent.winfo_rootx(), parent.winfo_rooty()
        pw, ph = parent.winfo_width(), parent.winfo_height()
        x = px + (pw - w) // 2
        y = py + (ph - h) // 3
        self.geometry(f"+{max(x, 0)}+{max(y, 0)}")

    def _clear_content(self) -> None:
        for child in self._content.winfo_children():
            child.destroy()

    # ---------------------------------------------------------- paso: hoja
    def _show_sheet_step(self, sheets: list[str]) -> None:
        self._header_label.config(text="Elegí la hoja del Excel")
        self._clear_content()

        tk.Label(self._content, bg=PANEL, fg=MUTED, font=FONT_SMALL,
                 anchor="w", justify="left",
                 text="El archivo tiene varias hojas. Elegí la que contiene "
                      "los datos a importar.").pack(fill="x", padx=18, pady=(14, 8))

        var = tk.StringVar(value=sheets[0])
        box = tk.Frame(self._content, bg=PANEL)
        box.pack(fill="x", padx=18)
        for s in sheets:
            tk.Radiobutton(box, text=s, variable=var, value=s, bg=PANEL,
                          fg=TEXT, font=FONT, activebackground=PANEL,
                          selectcolor=WHITE, anchor="w",
                          cursor="hand2").pack(fill="x", pady=2)

        footer = tk.Frame(self._content, bg=PANEL, padx=18)
        footer.pack(fill="x", side="bottom", pady=14)
        FlatButton(footer, "Cancelar", self.destroy, kind="secondary").pack(side="right")
        FlatButton(footer, "Continuar",
                  lambda: self._on_sheet_confirmed(var.get()),
                  kind="primary").pack(side="right", padx=(0, 10))

    def _on_sheet_confirmed(self, sheet: str) -> None:
        self.sheet = sheet
        self._show_mapping_step()

    # ------------------------------------------------------- paso: mapeo
    def _show_mapping_step(self) -> None:
        self._header_label.config(text="Mapear columnas")
        self._clear_content()

        self._headers = excel_import.read_headers(self.workbook, self.sheet)
        guess = excel_import.guess_mapping(self._headers)

        tk.Label(self._content, bg=PANEL, fg=MUTED, font=FONT_SMALL,
                 anchor="w", justify="left",
                 text="Indicá qué columna del Excel corresponde a cada dato. "
                      "Se sugirió una según el nombre de encabezado; "
                      "revisala antes de continuar.").pack(
            fill="x", padx=18, pady=(14, 10))

        form = tk.Frame(self._content, bg=PANEL)
        form.pack(fill="x", padx=18)
        form.columnconfigure(1, weight=1)

        fields = [
            ("code", "Código de pieza"),
            ("color", "Color"),
            ("grams", "Gramos de Carga"),
            ("speed", "Velocidad Inicio"),
        ]
        self._combo_vars = {}
        for row, (key, label) in enumerate(fields):
            tk.Label(form, text=label, bg=PANEL, fg=TEXT, font=FONT_BOLD,
                     anchor="w").grid(row=row, column=0, sticky="w", pady=8,
                                       padx=(0, 12))
            var = tk.StringVar()
            idx = guess.get(key)
            if idx is not None:
                var.set(self._headers[idx])
            self._combo_vars[key] = var
            combo = ttk.Combobox(form, textvariable=var, values=self._headers,
                                 state="readonly", font=FONT, width=32)
            combo.grid(row=row, column=1, sticky="we", pady=8)

        footer = tk.Frame(self._content, bg=PANEL, padx=18)
        footer.pack(fill="x", side="bottom", pady=14)
        FlatButton(footer, "Cancelar", self.destroy, kind="secondary").pack(side="right")
        FlatButton(footer, "Continuar", self._on_mapping_confirmed,
                  kind="primary").pack(side="right", padx=(0, 10))

    def _on_mapping_confirmed(self) -> None:
        chosen = {k: v.get() for k, v in self._combo_vars.items()}
        missing = [label for (key, label) in
                  (("code", "Código de pieza"), ("color", "Color"),
                   ("grams", "Gramos de Carga"), ("speed", "Velocidad Inicio"))
                  if not chosen[key]]
        if missing:
            messagebox.showwarning(
                "Falta mapear columnas",
                "Elegí una columna para: " + ", ".join(missing), parent=self)
            return
        if len(set(chosen.values())) != 4:
            messagebox.showwarning(
                "Columnas repetidas",
                "Cada dato debe mapearse a una columna distinta.", parent=self)
            return

        col_index = {k: self._headers.index(v) for k, v in chosen.items()}
        try:
            rows = excel_import.read_rows(
                self.workbook, self.sheet,
                col_code=col_index["code"], col_color=col_index["color"],
                col_grams=col_index["grams"], col_speed=col_index["speed"])
        except Exception as exc:
            messagebox.showerror("Error al leer el Excel", str(exc), parent=self)
            return

        self.diffs, self.unmatched, self.unchanged = self._compute_diffs(rows)
        self._show_diff_step()

    def _compute_diffs(self, rows: list[excel_import.ExcelRow]):
        by_index: dict[int, dict] = {}
        unmatched: list[str] = []
        unchanged = 0

        for row in rows:
            code_norm = excel_import.normalize_code(row.raw_code)
            if not code_norm:
                continue
            idx = self.store.find_code(code_norm)
            match_kind = "exact"
            if idx == -1:
                sig = code_signature(code_norm)
                if sig:
                    candidates = [
                        i for i, r in enumerate(self.store.recipes)
                        if not r.is_placeholder and code_signature(r.code) == sig
                    ]
                    if len(candidates) == 1:
                        idx = candidates[0]
                        match_kind = "approx"
            if idx == -1:
                unmatched.append(code_norm)
                continue

            new_color = excel_import.normalize_int(row.raw_color)
            new_grams = excel_import.normalize_int(row.raw_grams)
            new_speed = excel_import.normalize_int(row.raw_speed)
            r = self.store.recipes[idx]

            differs = (
                (new_color is not None and new_color != r.color) or
                (new_grams is not None and new_grams != r.grams) or
                (new_speed is not None and new_speed != r.speed)
            )
            if differs:
                by_index[idx] = {
                    "idx": idx, "code": r.code, "match_kind": match_kind,
                    "old": (r.color, r.grams, r.speed),
                    "new": (new_color, new_grams, new_speed),
                }
            else:
                unchanged += 1

        diffs = sorted(by_index.values(), key=lambda d: d["code"].upper())
        return diffs, unmatched, unchanged

    # -------------------------------------------------------- paso: diff
    def _show_diff_step(self) -> None:
        self._header_label.config(text="Revisar cambios")
        self._clear_content()

        summary_parts = [f"{len(self.diffs)} registro(s) con diferencias"]
        if self.unchanged:
            summary_parts.append(f"{self.unchanged} sin cambios")
        if self.unmatched:
            summary_parts.append(
                f"{len(self.unmatched)} código(s) no encontrados en el catálogo")
        tk.Label(self._content, bg=PANEL, fg=MUTED, font=FONT_SMALL,
                 anchor="w", justify="left",
                 text=" · ".join(summary_parts)).pack(
            fill="x", padx=18, pady=(12, 4))

        if not self.diffs:
            tk.Label(self._content, bg=PANEL, fg=TEXT, font=FONT,
                     text="No hay registros con valores distintos a los "
                          "actuales.").pack(padx=18, pady=20)
            footer = tk.Frame(self._content, bg=PANEL, padx=18)
            footer.pack(fill="x", side="bottom", pady=14)
            if self.unmatched:
                FlatButton(footer, "Ver no encontrados", self._show_unmatched,
                          kind="secondary").pack(side="left")
            FlatButton(footer, "Cerrar", self.destroy, kind="primary").pack(side="right")
            return

        toolbar = tk.Frame(self._content, bg=PANEL, padx=18)
        toolbar.pack(fill="x", pady=(0, 6))
        self._diff_vars: dict[int, tk.BooleanVar] = {}
        FlatButton(toolbar, "Seleccionar todos",
                  lambda: self._set_all_diffs(True), kind="ghost").pack(side="left")
        FlatButton(toolbar, "Ninguno",
                  lambda: self._set_all_diffs(False), kind="ghost").pack(
            side="left", padx=(6, 0))
        if self.unmatched:
            FlatButton(toolbar, f"Ver no encontrados ({len(self.unmatched)})",
                      self._show_unmatched, kind="secondary").pack(side="right")

        wrap = tk.Frame(self._content, bg=PANEL, padx=18)
        wrap.pack(fill="both", expand=True)
        canvas, inner = build_scrollable_canvas(self, wrap)

        field_labels = ("Color", "Gramos de Carga", "Velocidad Inicio")
        for d in self.diffs:
            card = tk.Frame(inner, bg=WHITE, highlightthickness=1,
                            highlightbackground=BORDER)
            card.pack(fill="x", pady=(0, 10), padx=(0, 14))

            head = tk.Frame(card, bg=WHITE)
            head.pack(fill="x", padx=12, pady=(8, 2))
            var = tk.BooleanVar(value=False)
            self._diff_vars[d["idx"]] = var
            tk.Checkbutton(head, variable=var, bg=WHITE, activebackground=WHITE,
                          selectcolor=WHITE, bd=0, highlightthickness=0,
                          cursor="hand2").pack(side="left")
            title = d["code"]
            if d["match_kind"] == "approx":
                title += "  (coincidencia aproximada por ceros — revisar)"
            tk.Label(head, text=title, bg=WHITE, fg=GREEN_DARK, font=FONT_BOLD,
                     anchor="w").pack(side="left", fill="x", expand=True)

            for label, old, new in zip(field_labels, d["old"], d["new"]):
                row = tk.Frame(card, bg=WHITE)
                row.pack(fill="x", padx=12, pady=1)
                tk.Label(row, text=label, bg=WHITE, fg=MUTED, font=FONT_SMALL,
                         width=18, anchor="w").pack(side="left")
                if new is None:
                    text, color = f"{old}  (sin dato en Excel, no se modifica)", MUTED
                elif new != old:
                    text, color = f"{old}  →  {new}", GREEN_DARK
                else:
                    text, color = f"{old}", TEXT
                font = FONT_BOLD if (new is not None and new != old) else FONT
                tk.Label(row, text=text, bg=WHITE, fg=color, font=font,
                         anchor="w").pack(side="left")
            tk.Frame(card, bg=WHITE, height=6).pack()

        footer = tk.Frame(self._content, bg=PANEL, padx=18)
        footer.pack(fill="x", side="bottom", pady=14)
        FlatButton(footer, "Cerrar", self.destroy, kind="secondary").pack(side="right")
        FlatButton(footer, "Aplicar seleccionados", self._on_apply_diffs,
                  kind="primary").pack(side="right", padx=(0, 10))

    def _set_all_diffs(self, value: bool) -> None:
        for var in self._diff_vars.values():
            var.set(value)

    def _show_unmatched(self) -> None:
        preview = "\n".join(self.unmatched[:40])
        if len(self.unmatched) > 40:
            preview += f"\n… y {len(self.unmatched) - 40} más"
        messagebox.showinfo(
            "Códigos no encontrados",
            "Estos códigos del Excel no existen en el catálogo actual y se "
            f"ignoraron:\n\n{preview}", parent=self)

    def _on_apply_diffs(self) -> None:
        selected = [d for d in self.diffs if self._diff_vars[d["idx"]].get()]
        if not selected:
            messagebox.showinfo("Sin selección",
                                "No marcaste ningún registro para aplicar.",
                                parent=self)
            return
        preview = ", ".join(d["code"] for d in selected[:6])
        if len(selected) > 6:
            preview += " …"
        if not messagebox.askyesno(
                "Confirmar importación",
                f"¿Aplicar {len(selected)} cambio(s)?\n\n{preview}", parent=self):
            return
        for d in selected:
            r = self.store.recipes[d["idx"]]
            new_color, new_grams, new_speed = d["new"]
            self.store.update(
                d["idx"], r.code,
                new_color if new_color is not None else r.color,
                new_grams if new_grams is not None else r.grams,
                new_speed if new_speed is not None else r.speed,
            )
        self.applied_any = True
        self.destroy()


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title(APP_TITLE)
        self.configure(bg=BG)
        self.geometry("980x640")
        self.minsize(820, 520)

        # --- Rutas de datos ---------------------------------------------------
        self.data_dir = app_data_dir()
        self.path_original = os.path.join(self.data_dir, "original.csv")
        self.path_actual = os.path.join(self.data_dir, "actual.csv")
        self._seed_data_files()

        self.store = RecipeStore.load(self.path_actual)
        self.show_placeholders = tk.BooleanVar(value=False)
        self.search_var = tk.StringVar()
        self.search_var.trace_add("write", lambda *_: self.refresh_table())
        self._sort_col: str | None = None
        self._sort_reverse = False

        self._setup_style()
        self._build_ui()
        self.refresh_table()

        self.bind("<Control-n>", lambda e: self.on_new())
        self.bind("<Control-f>", lambda e: self.search_entry.focus_set())

    # ------------------------------------------------------------------ datos
    def _seed_data_files(self) -> None:
        factory = resource_path(FACTORY_CSV)
        if not os.path.exists(self.path_original):
            shutil.copyfile(factory, self.path_original)
        if not os.path.exists(self.path_actual):
            shutil.copyfile(self.path_original, self.path_actual)

    def _autosave(self) -> None:
        self.store.save(self.path_actual)
        self._set_status("Cambios guardados en actual.csv", ok=True)

    # ------------------------------------------------------------------ estilo
    def _setup_style(self) -> None:
        style = ttk.Style(self)
        style.theme_use("clam")
        style.configure("Treeview",
                        background=WHITE, fieldbackground=WHITE, foreground=TEXT,
                        rowheight=30, font=FONT, borderwidth=0)
        style.configure("Treeview.Heading",
                        background=GREEN_LIGHT, foreground=GREEN_DEEP,
                        font=FONT_BOLD, relief="flat", padding=(8, 8))
        style.map("Treeview.Heading",
                  background=[("active", "#D8E8D2")])
        style.map("Treeview",
                  background=[("selected", GREEN)],
                  foreground=[("selected", WHITE)])
        style.configure("Vertical.TScrollbar", background=BG, troughcolor=BG,
                        borderwidth=0, arrowcolor=MUTED)

    # --------------------------------------------------------------------- UI
    def _build_ui(self) -> None:
        # Cabecera
        header = tk.Frame(self, bg=GREEN, height=64)
        header.pack(fill="x")
        header.pack_propagate(False)
        tk.Label(header, text="Configurador Máquina 232", bg=GREEN, fg=WHITE,
                 font=FONT_TITLE).pack(side="left", padx=22)
        tk.Label(header, text="Editor de recetas · calibración de aceite y velocidad",
                 bg=GREEN, fg="#DCEBD6", font=FONT_SMALL).pack(side="left", pady=(4, 0))

        # Barra de herramientas
        toolbar = tk.Frame(self, bg=BG, padx=16, pady=12)
        toolbar.pack(fill="x")

        search_box = tk.Frame(toolbar, bg=WHITE, highlightthickness=1,
                              highlightbackground=BORDER)
        search_box.pack(side="left")
        tk.Label(search_box, text="🔍", bg=WHITE, fg=MUTED,
                 font=FONT).pack(side="left", padx=(8, 0))
        self.search_entry = tk.Entry(search_box, textvariable=self.search_var,
                                     font=FONT, width=28, relief="flat", bd=0,
                                     bg=WHITE, fg=TEXT)
        self.search_entry.pack(side="left", padx=6, pady=6)
        self.search_entry.insert(0, "")
        tk.Label(search_box, text="Buscar por código", bg=WHITE, fg=MUTED,
                 font=FONT_SMALL).pack(side="left", padx=(0, 8))

        FlatButton(toolbar, "＋ Nuevo", self.on_new, kind="primary").pack(
            side="left", padx=(16, 6))
        FlatButton(toolbar, "Editar", self.on_edit, kind="ghost").pack(side="left", padx=6)
        FlatButton(toolbar, "Eliminar", self.on_delete, kind="danger").pack(
            side="left", padx=6)
        FlatButton(toolbar, "Duplicados", self.on_duplicates, kind="secondary").pack(
            side="left", padx=6)
        FlatButton(toolbar, "Importar cambios", self.on_import, kind="secondary").pack(
            side="left", padx=6)

        # Exportar (menú)
        self.export_btn = FlatButton(toolbar, "Exportar ▾", self._show_export_menu,
                                     kind="secondary")
        self.export_btn.pack(side="right")
        FlatButton(toolbar, "Restaurar original", self.on_restore,
                   kind="secondary").pack(side="right", padx=(0, 8))
        self.export_menu = tk.Menu(self, tearoff=0, bg=WHITE, fg=TEXT,
                                   activebackground=GREEN_LIGHT, activeforeground=TEXT,
                                   font=FONT, bd=1, relief="solid")
        self.export_menu.add_command(label="Exportar CSV actual (con cambios)…",
                                     command=lambda: self.on_export("actual"))
        self.export_menu.add_command(label="Exportar CSV original (sin cambios)…",
                                     command=lambda: self.on_export("original"))

        # Fila de filtro
        filt = tk.Frame(self, bg=BG, padx=16)
        filt.pack(fill="x")
        tk.Checkbutton(filt, text="Mostrar slots vacíos (_DATA_)",
                       variable=self.show_placeholders, command=self.refresh_table,
                       bg=BG, fg=MUTED, font=FONT_SMALL, activebackground=BG,
                       selectcolor=WHITE, bd=0, highlightthickness=0,
                       cursor="hand2").pack(side="left")

        # Tabla
        table_wrap = tk.Frame(self, bg=BORDER, padx=1, pady=1)
        table_wrap.pack(fill="both", expand=True, padx=16, pady=(8, 8))

        cols = ("pos", "code", "color", "grams", "speed")
        headings = {
            "pos": "#", "code": "Código", "color": "Color",
            "grams": "Gramos de Carga", "speed": "Velocidad Inicio",
        }
        widths = {"pos": 70, "code": 260, "color": 90, "grams": 160, "speed": 160}
        anchors = {"pos": "center", "code": "w", "color": "center",
                   "grams": "center", "speed": "center"}

        self.tree = ttk.Treeview(table_wrap, columns=cols, show="headings",
                                 selectmode="extended")
        for c in cols:
            self.tree.heading(c, text=headings[c],
                              command=lambda cc=c: self._sort_by(cc))
            self.tree.column(c, width=widths[c], anchor=anchors[c],
                             stretch=(c == "code"))
        self.tree.tag_configure("placeholder", foreground=MUTED)
        self.tree.tag_configure("odd", background="#FAFBF9")

        vsb = ttk.Scrollbar(table_wrap, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=vsb.set)
        vsb.pack(side="right", fill="y")
        self.tree.pack(side="left", fill="both", expand=True)
        self.tree.bind("<Double-1>", lambda e: self.on_edit())
        self.tree.bind("<Return>", lambda e: self.on_edit())
        self.tree.bind("<Delete>", lambda e: self.on_delete())

        # Barra de estado
        self.status = tk.Frame(self, bg=WHITE, height=30,
                               highlightthickness=1, highlightbackground=BORDER)
        self.status.pack(fill="x", side="bottom")
        self.status.pack_propagate(False)
        self.status_label = tk.Label(self.status, text="", bg=WHITE, fg=MUTED,
                                     font=FONT_SMALL, anchor="w")
        self.status_label.pack(side="left", padx=12)
        self.count_label = tk.Label(self.status, text="", bg=WHITE, fg=GREEN_DARK,
                                    font=FONT_SMALL, anchor="e")
        self.count_label.pack(side="right", padx=12)

    # --------------------------------------------------------------- tabla
    def _visible_rows(self) -> list[tuple[int, Recipe]]:
        query = self.search_var.get().strip().lower()
        show_ph = self.show_placeholders.get()
        rows = []
        for i, r in enumerate(self.store.recipes):
            if not show_ph and r.is_placeholder:
                continue
            if query and query not in r.code.lower():
                continue
            rows.append((i, r))
        return rows

    def refresh_table(self) -> None:
        selected_indices = {int(iid) for iid in self.tree.selection()} \
            if hasattr(self, "tree") else set()
        self.tree.delete(*self.tree.get_children())

        rows = self._visible_rows()
        if self._sort_col:
            key = {
                "pos": lambda t: t[0],
                "code": lambda t: t[1].code.lower(),
                "color": lambda t: t[1].color,
                "grams": lambda t: t[1].grams,
                "speed": lambda t: t[1].speed,
            }[self._sort_col]
            rows.sort(key=key, reverse=self._sort_reverse)

        for n, (i, r) in enumerate(rows):
            tags = []
            if r.is_placeholder:
                tags.append("placeholder")
            if n % 2:
                tags.append("odd")
            self.tree.insert("", "end", iid=str(i), tags=tuple(tags),
                             values=(n + 1, r.code, r.color, r.grams, r.speed))
        for iid in selected_indices:
            if self.tree.exists(str(iid)):
                self.tree.selection_add(str(iid))

        total = len(self.store.recipes)
        reales = self.store.count_real()
        shown = len(rows)
        self.count_label.config(
            text=f"{shown} mostrados · {reales} piezas reales · {total} slots")

    def _sort_by(self, col: str) -> None:
        if self._sort_col == col:
            self._sort_reverse = not self._sort_reverse
        else:
            self._sort_col, self._sort_reverse = col, False
        self.refresh_table()

    def _selected_index(self) -> int | None:
        sel = self.tree.selection()
        if not sel:
            return None
        return int(sel[0])

    def _set_status(self, text: str, ok: bool = False) -> None:
        self.status_label.config(text=text, fg=(GREEN_DARK if ok else MUTED))

    # --------------------------------------------------------------- acciones
    def on_new(self) -> None:
        template = Recipe(code="", color=1, grams=0, speed=350)
        dlg = RecipeDialog(self, self.store, "Nuevo registro", recipe=template,
                           edit_index=None)
        if dlg.result:
            self.store.add(dlg.result)
            self._autosave()
            self.refresh_table()
            new_index = len(self.store.recipes) - 1
            if self.tree.exists(str(new_index)):
                self.tree.selection_set(str(new_index))
                self.tree.see(str(new_index))
            self._set_status(f"Registro «{dlg.result.code}» agregado al final.", ok=True)

    def on_edit(self) -> None:
        idx = self._selected_index()
        if idx is None:
            messagebox.showinfo("Editar", "Seleccioná un registro para editar.")
            return
        current = self.store.recipes[idx]
        dlg = RecipeDialog(self, self.store, "Modificar registro",
                           recipe=current, edit_index=idx)
        if dlg.result:
            r = dlg.result
            self.store.update(idx, r.code, r.color, r.grams, r.speed)
            self._autosave()
            self.refresh_table()
            if self.tree.exists(str(idx)):
                self.tree.selection_set(str(idx))
            self._set_status(f"Registro «{r.code}» modificado.", ok=True)

    def on_delete(self) -> None:
        sel = self.tree.selection()
        if not sel:
            messagebox.showinfo("Eliminar", "Seleccioná uno o más registros.")
            return
        indices = sorted((int(iid) for iid in sel), reverse=True)
        codes = [self.store.recipes[i].code for i in indices]
        preview = ", ".join(codes[:5]) + (" …" if len(codes) > 5 else "")
        if not messagebox.askyesno(
                "Confirmar eliminación",
                f"¿Eliminar {len(indices)} registro(s)?\n\n{preview}"):
            return
        for i in indices:
            self.store.delete(i)
        self._autosave()
        self.refresh_table()
        self._set_status(f"{len(indices)} registro(s) eliminado(s).", ok=True)

    def on_duplicates(self) -> None:
        dlg = DuplicatesDialog(self, self.store)
        if dlg.deleted_any or dlg.reviewed_any:
            self._autosave()
            self.refresh_table()
            if dlg.deleted_any:
                self._set_status("Duplicados eliminados según tu selección.", ok=True)
            else:
                self._set_status("Revisión de duplicados guardada.", ok=True)

    def on_import(self) -> None:
        if excel_import is None:
            messagebox.showerror(
                "Falta un componente",
                "Para importar desde Excel se necesita el paquete "
                "'openpyxl', que no está instalado.\n\n"
                "Instalalo con:\n  py -m pip install openpyxl\n\n"
                "o volvé a ejecutar run.bat / build.bat, que lo instalan "
                "automáticamente.")
            return
        path = filedialog.askopenfilename(
            title="Importar cambios desde Excel",
            filetypes=[("Excel", "*.xlsx *.xlsm"), ("Todos los archivos", "*.*")],
        )
        if not path:
            return
        try:
            workbook = excel_import.open_workbook(path)
        except Exception as exc:
            messagebox.showerror("Error al abrir el Excel",
                                 f"No se pudo leer el archivo:\n\n{exc}")
            return
        try:
            dlg = ImportDialog(self, self.store, workbook, os.path.basename(path))
        finally:
            workbook.close()
        if dlg.applied_any:
            self._autosave()
            self.refresh_table()
            self._set_status("Cambios importados según tu selección.", ok=True)

    def on_restore(self) -> None:
        if not messagebox.askyesno(
                "Restaurar original",
                "Se descartarán TODOS los cambios y se volverá al archivo "
                "original de fábrica.\n\n¿Continuar?"):
            return
        shutil.copyfile(self.path_original, self.path_actual)
        self.store = RecipeStore.load(self.path_actual)
        self.refresh_table()
        self._set_status("Archivo restaurado al original de fábrica.", ok=True)

    def _show_export_menu(self) -> None:
        x = self.export_btn.winfo_rootx()
        y = self.export_btn.winfo_rooty() + self.export_btn.winfo_height()
        self.export_menu.tk_popup(x, y)

    def on_export(self, which: str) -> None:
        label = "actual (con cambios)" if which == "actual" else "original (sin cambios)"
        dest = filedialog.asksaveasfilename(
            title=f"Exportar CSV {label}",
            defaultextension=".csv",
            initialfile="recetas232.csv",
            filetypes=[("Archivo CSV", "*.csv"), ("Todos los archivos", "*.*")],
        )
        if not dest:
            return
        try:
            if which == "actual":
                self.store.save(self.path_actual)  # garantiza estado al día
                # El archivo de trabajo interno incluye la fila de revisión
                # de duplicados; el exportado para el HMI debe mantener el
                # formato ORIGINAL de la máquina, sin esa fila.
                with open(dest, "w", encoding="utf-8", newline="") as f:
                    f.write(self.store.to_csv_text(include_internal=False))
            else:
                shutil.copyfile(self.path_original, dest)
        except OSError as exc:
            messagebox.showerror("Error al exportar", str(exc))
            return
        self._set_status(f"Exportado a: {dest}", ok=True)
        messagebox.showinfo("Exportación completa",
                            f"Se exportó el CSV {label} a:\n\n{dest}")


def main() -> None:
    enable_dpi_awareness()
    app = App()
    app.mainloop()


if __name__ == "__main__":
    main()
