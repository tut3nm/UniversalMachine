"""
app.py — Configurador de Parámetros de Planta
=============================================
Interfaz de escritorio (Tkinter + ttkbootstrap) genérica: administra archivos
de parámetros de distintas máquinas, cada una descrita por un perfil JSON (ver
profiles/ y profile.py). La UI (columnas de la tabla, campos de los diálogos)
se construye en tiempo de ejecución a partir del perfil elegido.

Motor de datos: datastore.DataStore (guardado byte-fiel al formato original).
Metadatos propios de la app (marca "no es duplicado"): metadata.Sidecar, en un
archivo aparte que nunca se mezcla con el CSV de la máquina.

UI: se usa ttkbootstrap (liviana, ~1.7 MB, sin dependencias compiladas) para
widgets modernos (botones planos, tooltips, notificaciones tipo "toast",
combos/checks/switches con estilo) sobre un tema propio en tonos verde hoja /
blanco / gris.
"""

from __future__ import annotations

import csv
import json
import os
import re
import shutil
import sys
from dataclasses import dataclass, field
from datetime import datetime, timedelta
import tkinter as tk
from tkinter import filedialog

import ttkbootstrap as tb
from ttkbootstrap.dialogs import Messagebox, Querybox
from ttkbootstrap.style import ThemeDefinition
from ttkbootstrap.widgets import ToastNotification, ToolTip

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from profile import Campo, Profile, ProfileError  # noqa: E402
from datastore import DataStore                    # noqa: E402
from metadata import Sidecar                        # noqa: E402
from io_seguro import escribir_atomico, verificar_contenido, escribir_bytes_atomico, copiar_atomico  # noqa: E402
import validacion                                    # noqa: E402
import backups                                       # noqa: E402
import historial                                      # noqa: E402
import paths                                        # noqa: E402
import profile_builder                              # noqa: E402
import importacion                                   # noqa: E402
import arranque                                      # noqa: E402
import log_config                                    # noqa: E402
import version                                        # noqa: E402
import diferencias                                    # noqa: E402
import salud                                          # noqa: E402
import deteccion_externa                              # noqa: E402
import instancia                                      # noqa: E402
import informe                                        # noqa: E402
import import_mapeos                                  # noqa: E402
import filtros                                        # noqa: E402
import panel_multi_maquina                            # noqa: E402
try:
    import excel_import                             # noqa: E402
except ImportError:
    excel_import = None

APP_TITLE = "Configurador de Parámetros de Planta"
LIMITE_DESHACER = 50


@dataclass
class CambioRegistro:
    """Un cambio puntual sobre UN registro (alta/modificación/baja), la
    unidad mínima que se registra en el historial (2.2) y que se puede
    deshacer (2.3). `anteriores`/`nuevos` son snapshots completos del
    registro (dict), no solo los campos que cambiaron, para poder revertir
    sin ambigüedad."""
    accion: str  # "alta" | "modificacion" | "baja"
    clave: str
    anteriores: dict | None = None
    nuevos: dict | None = None


@dataclass
class ComandoDeshacer:
    """Una acción del usuario, posiblemente compuesta por varios
    CambioRegistro (p. ej. una importación que aplica varias altas/bajas/
    modificaciones a la vez): se deshace/rehace como una sola unidad."""
    descripcion: str
    cambios: list[CambioRegistro] = field(default_factory=list)

# --- Paleta: blanco, grises y verde hoja -------------------------------------
WHITE = "#FFFFFF"
BG = "#F4F6F3"
PANEL = "#FFFFFF"
BORDER = "#D7DCD5"
TEXT = "#2B2F2B"
MUTED = "#727A71"
GREEN = "#4E9A51"
GREEN_DARK = "#3C7A3F"
GREEN_DEEP = "#2F5F31"
GREEN_LIGHT = "#E7F1E3"
RED = "#B4472E"
RED_DARK = "#8F3623"
AMBER = "#C77A00"

FONT = ("Segoe UI", 10)
FONT_BOLD = ("Segoe UI", 10, "bold")
FONT_TITLE = ("Segoe UI Semibold", 16)
FONT_SMALL = ("Segoe UI", 9)

THEME_COLORS = {
    "primary": GREEN, "secondary": MUTED, "success": GREEN_DARK,
    "info": GREEN_DEEP, "warning": AMBER, "danger": RED,
    "light": BG, "dark": TEXT, "bg": WHITE, "fg": TEXT,
    "selectbg": GREEN, "selectfg": WHITE, "border": BORDER,
    "inputfg": TEXT, "inputbg": WHITE, "active": GREEN_LIGHT,
}


def enable_dpi_awareness() -> None:
    try:
        from ctypes import windll
        windll.shcore.SetProcessDpiAwareness(1)
    except Exception:
        pass


def apply_theme(window: tb.Window) -> None:
    """Registra y aplica el tema propio 'planta' (verde hoja / blanco / gris)
    sobre la ventana raíz de ttkbootstrap."""
    style = window.style
    if "planta" not in style.theme_names():
        style.register_theme(
            ThemeDefinition(name="planta", themetype="light", colors=THEME_COLORS))
    style.theme_use("planta")
    style.configure("TCheckbutton", font=FONT)
    style.configure("Treeview", rowheight=30, font=FONT)
    style.configure("Treeview.Heading", font=FONT_BOLD)


def button(parent, text, command=None, kind="secondary", small=False,
           tooltip=None, **kw) -> tb.Button:
    """Botón estandarizado de la app. `kind` mapea a un bootstyle:
      primary   -> acción principal (verde sólido)
      danger    -> acción destructiva (rojo sólido)
      secondary -> acción neutra frecuente (gris sólido)
      outline   -> acción secundaria/utilitaria (borde verde)
      ghost     -> acción terciaria muy sutil (link)
    """
    styles = {"primary": "success", "danger": "danger", "secondary": "secondary",
              "outline": "outline-success", "ghost": "link"}
    opts = dict(bootstyle=styles.get(kind, kind))
    if small:
        opts["padding"] = (8, 3)
    opts.update(kw)
    btn = tb.Button(parent, text=text, command=command, **opts)
    if tooltip:
        ToolTip(btn, text=tooltip, bootstyle="secondary-inverse")
    return btn


def build_scrollable_canvas(dialog: tk.Toplevel, container: tk.Widget,
                            h_scroll: bool = False):
    """Área con scroll vertical (y opcionalmente horizontal) con rueda del
    mouse incluida, que se desregistra sola al destruirse el diálogo."""
    outer = tk.Frame(container, bg=PANEL)
    outer.pack(fill="both", expand=True)
    canvas = tk.Canvas(outer, bg=PANEL, highlightthickness=0)
    vsb = tb.Scrollbar(outer, orient="vertical", command=canvas.yview,
                       bootstyle="round")
    inner = tk.Frame(canvas, bg=PANEL)
    win_id = canvas.create_window((0, 0), window=inner, anchor="nw")
    inner.bind("<Configure>",
               lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
    canvas.configure(yscrollcommand=vsb.set)

    if h_scroll:
        hsb = tb.Scrollbar(outer, orient="horizontal", command=canvas.xview,
                           bootstyle="round")
        canvas.configure(xscrollcommand=hsb.set)
        hsb.pack(side="bottom", fill="x")
    else:
        # Sin scroll horizontal el inner se estira al ancho del canvas para
        # que labels/entries no queden apilados en un ancho mínimo.
        def _fit_width(event):
            canvas.itemconfig(win_id, width=event.width)
        canvas.bind("<Configure>", _fit_width)

    canvas.pack(side="left", fill="both", expand=True)
    vsb.pack(side="right", fill="y")

    def _on_wheel(event):
        canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")
    canvas.bind_all("<MouseWheel>", _on_wheel)

    if h_scroll:
        def _on_shift_wheel(event):
            canvas.xview_scroll(int(-1 * (event.delta / 120)), "units")
        canvas.bind_all("<Shift-MouseWheel>", _on_shift_wheel)

    def _unbind_wheel(event) -> None:
        if event.widget is dialog:
            canvas.unbind_all("<MouseWheel>")
            if h_scroll:
                canvas.unbind_all("<Shift-MouseWheel>")
    dialog.bind("<Destroy>", _unbind_wheel, add="+")
    return canvas, inner


def _center_dialog(dialog: tk.Toplevel, parent) -> None:
    dialog.update_idletasks()
    w, h = dialog.winfo_width(), dialog.winfo_height()
    if str(parent.wm_state()) == "withdrawn":
        # Con la ventana padre oculta, sus medidas son el tamaño por
        # defecto (200x200) y no las reales: centramos contra la pantalla
        # para no terminar posicionando el diálogo fuera de vista.
        px, py = 0, 0
        pw, ph = parent.winfo_screenwidth(), parent.winfo_screenheight()
    else:
        px, py = parent.winfo_rootx(), parent.winfo_rooty()
        pw, ph = parent.winfo_width(), parent.winfo_height()
    x = px + (pw - w) // 2
    y = py + (ph - h) // 3
    dialog.geometry(f"+{max(x, 0)}+{max(y, 0)}")


def confirm(parent, title: str, message: str) -> bool:
    """Diálogo Sí/No consistente con el tema (etiquetas fijas en español, sin
    depender de la localización del sistema operativo)."""
    result = Messagebox.yesno(message, title, parent=parent, alert=False,
                              buttons=["No:secondary", "Sí:success"])
    return result == "Sí"


def preguntar_opciones(parent, title: str, message: str, opciones: list[str]) -> str | None:
    """Diálogo con N botones a elección (p. ej. para ofrecer 'Reintentar' /
    'Restaurar el original' / 'Cancelar' ante un error de carga). Usa el
    mismo MessageDialog que confirm() — Messagebox.yesno acepta una lista
    arbitraria de botones pese al nombre. Cada elemento de `opciones` puede
    llevar ':estilo' (ej. "Cancelar:danger"); se devuelve la etiqueta SIN el
    sufijo de estilo, o None si se cerró el diálogo sin elegir nada."""
    return Messagebox.yesno(message, title, parent=parent, alert=False, buttons=opciones)


def warn(parent, title: str, message: str) -> None:
    Messagebox.show_warning(message, title, parent=parent)


def error(parent, title: str, message: str) -> None:
    Messagebox.show_error(message, title, parent=parent)


def info(parent, title: str, message: str) -> None:
    Messagebox.show_info(message, title, parent=parent)


def toast(root, message: str, kind: str = "success") -> None:
    """Notificación breve no bloqueante en la esquina, para confirmar que una
    acción se completó sin interrumpir al usuario con un diálogo modal."""
    styles = {"success": "success", "warning": "warning", "danger": "danger"}
    ToastNotification(title="Configurador de Planta", message=message,
                      duration=2600, bootstyle=styles.get(kind, "success"),
                      alert=False).show_toast()


# ============================================================================
#  Diálogo para eliminar máquina
# ============================================================================
class DeleteMachineDialog(tk.Toplevel):
    """Diálogo para seleccionar y eliminar una máquina."""

    def __init__(self, parent, profiles: list[Profile]):
        super().__init__(parent)
        self.profiles = profiles
        self.deleted = False
        self.deleted_id: str | None = None

        self.title("Eliminar máquina")
        self.configure(bg=PANEL)
        self.resizable(False, False)
        self.transient(parent)

        header = tk.Frame(self, bg=RED, height=52)
        header.pack(fill="x")
        header.pack_propagate(False)
        tk.Label(header, text="Eliminar máquina", bg=RED, fg=WHITE,
                 font=("Segoe UI Semibold", 13)).pack(side="left", padx=18)

        body = tk.Frame(self, bg=PANEL, padx=20, pady=16)
        body.pack(fill="both", expand=True)
        tk.Label(body, bg=PANEL, fg=MUTED, font=FONT_SMALL, anchor="w",
                 text="Seleccioná la máquina a eliminar. Se borrará permanentemente "
                      "el perfil, los datos y los metadatos.").pack(
            fill="x", pady=(0, 12))

        self._selected_id: str | None = None
        self._buttons: dict[str, tb.Button] = {}

        for prof in profiles:
            card = tk.Frame(body, bg=WHITE, highlightthickness=1,
                            highlightbackground=BORDER, cursor="hand2")
            card.pack(fill="x", pady=4, ipady=3)
            title_row = tk.Frame(card, bg=WHITE, cursor="hand2")
            title_row.pack(fill="x", padx=12, pady=(6, 0))
            tk.Label(title_row, text=prof.nombre, bg=WHITE, fg=GREEN_DARK,
                     font=FONT_BOLD, anchor="w", cursor="hand2").pack(side="left")
            if prof.descripcion:
                tk.Label(card, text=prof.descripcion, bg=WHITE, fg=MUTED,
                         font=FONT_SMALL, anchor="w", justify="left",
                         wraplength=320, cursor="hand2").pack(
                    fill="x", padx=12, pady=(0, 4))
            btn = button(card, "Seleccionar",
                        lambda p_id=prof.id: self._select(p_id),
                        kind="danger", small=True)
            btn.pack(fill="x", padx=12, pady=(0, 6))
            self._buttons[prof.id] = btn

        footer = tk.Frame(self, bg=PANEL, padx=20)
        footer.pack(fill="x", pady=(0, 16))
        button(footer, "Cancelar", self.destroy, kind="secondary").pack(side="right")
        self._delete_btn = button(footer, "Confirmar eliminación",
                                   self._confirm_delete, kind="danger")
        self._delete_btn.pack(side="right", padx=(0, 8))
        self._delete_btn.config(state="disabled")

        self.after(50, _center_dialog, self, parent)
        self.wait_visibility()
        self.grab_set()
        self.bind("<Escape>", lambda e: self.destroy())
        self.wait_window(self)

    def _select(self, prof_id: str) -> None:
        self._selected_id = prof_id
        self._delete_btn.config(state="normal")
        for pid, btn in self._buttons.items():
            btn.config(text="✓ Seleccionado" if pid == prof_id else "Seleccionar")

    def _confirm_delete(self) -> None:
        if not self._selected_id:
            return
        prof = next((p for p in self.profiles if p.id == self._selected_id), None)
        if not prof:
            return
        msg = (f"¿Eliminar permanentemente la máquina «{prof.nombre}»?\n\n"
               f"Se borrarán:\n"
               f"  • Perfil: {os.path.basename(prof.ruta)}\n"
               f"  • Datos y metadatos en la carpeta datos/{prof.id}/\n\n"
               "Esta acción no se puede deshacer.")
        if not confirm(self, "Confirmar eliminación", msg):
            return
        try:
            self._delete_profile_and_data(prof)
            self.deleted = True
            self.deleted_id = self._selected_id
            toast(self, f"Máquina «{prof.nombre}» eliminada.", kind="warning")
            self.destroy()
        except OSError as e:
            error(self, "Error al eliminar", f"No se pudo eliminar la máquina:\n\n{e}")

    def _delete_profile_and_data(self, prof: Profile) -> None:
        # Eliminar archivo de perfil
        if os.path.exists(prof.ruta):
            os.remove(prof.ruta)
        # Eliminar carpeta de datos
        data_dir = paths.data_dir_for(prof.id)
        if os.path.isdir(data_dir):
            shutil.rmtree(data_dir)


# ============================================================================
#  Selector de máquina
# ============================================================================
class MachineSelector(tk.Toplevel):
    """Navegador de documentos de configuración de máquinas: lista todos los
    perfiles disponibles (profiles/*.json) para elegir cuál administrar.
    Si `current_id` coincide con un perfil, lo marca como el activo."""

    def __init__(self, parent, profiles: list[Profile], current_id: str | None = None):
        super().__init__(parent)
        self.result: Profile | None = None
        self.profiles = profiles
        self.current_id = current_id
        self.edited_id: str | None = None  # id de la máquina cuyo formato se editó (si aplica)
        self.title("Máquinas")
        self.configure(bg=PANEL)
        self.resizable(False, False)
        self.transient(parent)

        self._build_body()

        self.after(50, _center_dialog, self, parent)
        self.wait_visibility()
        self.grab_set()
        self.bind("<Escape>", lambda e: self.destroy())
        self.wait_window(self)

    def _build_body(self) -> None:
        """Construye (o reconstruye) todo el contenido del diálogo a partir
        de self.profiles/self.current_id. Reconstruir acá adentro — en vez
        de volver a llamar __init__/wait_window sobre el mismo Toplevel ya
        armado — evita anidar wait_window() sobre la misma ventana, que deja
        un diálogo fantasma sin contenido e imposible de cerrar."""
        for w in self.winfo_children():
            w.destroy()

        header = tk.Frame(self, bg=GREEN, height=56)
        header.pack(fill="x")
        header.pack_propagate(False)
        tk.Label(header, text="Documentos de configuración de máquinas", bg=GREEN,
                 fg=WHITE, font=("Segoe UI Semibold", 13)).pack(side="left", padx=18)

        body = tk.Frame(self, bg=PANEL, padx=20, pady=16)
        body.pack(fill="both", expand=True)
        tk.Label(body, bg=PANEL, fg=MUTED, font=FONT_SMALL, anchor="w",
                 text="Elegí qué máquina administrar. Cada una guarda sus "
                      "propios datos y no se mezclan entre sí.").pack(
            fill="x", pady=(0, 10))
        for prof in self.profiles:
            is_current = prof.id == self.current_id
            card = tk.Frame(body, bg=WHITE, highlightthickness=(2 if is_current else 1),
                            highlightbackground=(GREEN if is_current else BORDER),
                            cursor="hand2")
            card.pack(fill="x", pady=5, ipady=4)
            title_row = tk.Frame(card, bg=WHITE, cursor="hand2")
            title_row.pack(fill="x", padx=14, pady=(8, 0))
            edit_btn = button(title_row, "✎ Editar formato",
                              lambda p=prof: self._on_edit_format(p),
                              kind="ghost", small=True,
                              tooltip="Ajustar qué filas/columnas son campos, su "
                                      "nombre y tipo de dato")
            edit_btn.pack(side="right")
            tk.Label(title_row, text=prof.nombre, bg=WHITE, fg=GREEN_DARK,
                     font=FONT_BOLD, anchor="w", cursor="hand2").pack(side="left")
            if is_current:
                tk.Label(title_row, text="  ●  máquina actual", bg=WHITE,
                         fg=GREEN, font=FONT_SMALL, cursor="hand2").pack(side="left")
            if prof.descripcion:
                tk.Label(card, text=prof.descripcion, bg=WHITE, fg=MUTED,
                         font=FONT_SMALL, anchor="w", justify="left",
                         wraplength=420, cursor="hand2").pack(
                    fill="x", padx=14, pady=(0, 8))
            clickable = [w for w in (card, *card.winfo_children(), *title_row.winfo_children())
                        if w is not edit_btn]
            for widget in clickable:
                widget.bind("<Button-1>", lambda e, p=prof: self._choose(p))
                widget.bind("<Enter>", lambda e, c=card: c.config(bg=GREEN_LIGHT))
                widget.bind("<Leave>", lambda e, c=card: c.config(bg=WHITE))

        footer = tk.Frame(self, bg=PANEL, padx=20)
        footer.pack(fill="x", pady=(0, 16))
        button(footer, "Cerrar", self.destroy, kind="secondary").pack(side="right")
        button(footer, "🗑 Eliminar", self._on_delete_machine, kind="danger",
              tooltip="Eliminar una máquina y sus datos").pack(side="right", padx=(0, 8))
        button(footer, "➕ Agregar máquina", self._on_add_machine, kind="primary",
              tooltip="Adjuntar el CSV de una máquina nueva y crear su "
                      "perfil").pack(side="left")

    def _on_add_machine(self) -> None:
        existing_ids = {p.id for p in self.profiles}
        dlg = WizardMachineDialog(self, existing_ids)
        if dlg.new_profile:
            self.result = dlg.new_profile
            self.destroy()

    def _choose(self, prof: Profile) -> None:
        self.result = prof
        self.destroy()

    def _on_delete_machine(self) -> None:
        if not self.profiles:
            warn(self, "Sin máquinas", "No hay máquinas para eliminar.")
            return
        dlg = DeleteMachineDialog(self, self.profiles)
        if dlg.deleted:
            # Refrescar la lista de perfiles eliminando la máquina borrada
            self.profiles = [p for p in self.profiles if p.id != dlg.deleted_id]
            self._build_body()

    def _on_edit_format(self, prof: Profile) -> None:
        existing_ids = {p.id for p in self.profiles} - {prof.id}
        dlg = WizardMachineDialog(self, existing_ids, existing_profile=prof)
        if dlg.new_profile:
            # Reemplazar el perfil editado en la lista y reconstruir el
            # contenido para reflejar el nombre/descripción actualizados.
            self.profiles = [dlg.new_profile if p.id == prof.id else p
                             for p in self.profiles]
            self.edited_id = dlg.new_profile.id
            self._build_body()


# ============================================================================
#  Wizard de alta de máquina nueva
#  (archivo -> orientación -> campos -> validación byte-perfecta -> confirmar)
# ============================================================================
TIPOS_UI = [
    ("texto", "Texto"),
    ("entero", "Entero"),
    ("entero_ceros", "Entero con ceros a la izquierda"),
    ("decimal", "Decimal"),
]
TIPO_LABEL = dict(TIPOS_UI)
TIPO_POR_LABEL = {v: k for k, v in TIPOS_UI}


class WizardMachineDialog(tk.Toplevel):
    """Wizard de alta de máquina: adjunta un CSV de muestra y guía al
    usuario para describir su formato campo por campo (una cantidad
    indefinida de filas/columnas, cada una con nombre y tipo de dato
    propios), antes de generar el perfil JSON.

    Cualquier fila/columna del archivo que NO se elija como campo visible
    se conserva igual como campo OCULTO (visible=False): viaja con cada
    registro y se preserva byte a byte, pero nunca se muestra ni se edita
    en la tabla principal. Antes de permitir confirmar el alta, el wizard
    reconstruye el archivo con el perfil armado y lo compara byte a byte
    contra el original — si no coincide, no deja continuar."""

    def __init__(self, parent, existing_ids: set[str],
                 existing_profile: Profile | None = None):
        super().__init__(parent)
        self.existing_ids = existing_ids
        self.new_profile: Profile | None = None
        self._edit_mode = existing_profile is not None
        self._existing_profile = existing_profile
        self._clave_idx_original: int | None = None
        self._clave_changed = False

        self._csv_path: str | None = None
        self._info: dict | None = None
        self._grid: list[list[str]] | None = None
        self._orientacion = tk.StringVar(value="columnas")
        self._clave_idx = tk.StringVar(value="0")
        self._row_state: dict[int, dict] = {}   # idx -> vars (incluir/nombre/tipo/...)
        self._perfil_dict: dict | None = None
        # Offsets de estructura: por default los de un CSV típico; en modo
        # edición se toman del perfil existente (por si usa otros).
        self._primera_col = 1
        self._header_row = 0
        self._primera_fila_datos = 1

        titulo = "Editar formato de máquina" if self._edit_mode else "Agregar máquina"
        self.title(titulo)
        self.configure(bg=PANEL)
        self.resizable(True, True)
        self.transient(parent)
        self.geometry("860x620")

        self._header_frame = tk.Frame(self, bg=GREEN, height=56)
        self._header_frame.pack(fill="x")
        self._header_frame.pack_propagate(False)
        self._header_label = tk.Label(self._header_frame, text=titulo,
                                      bg=GREEN, fg=WHITE, font=("Segoe UI Semibold", 13))
        self._header_label.pack(side="left", padx=18)
        self._content = tk.Frame(self, bg=PANEL)
        self._content.pack(fill="both", expand=True)

        if self._edit_mode:
            if not self._load_existing_profile(existing_profile):
                self.destroy()
                return
        else:
            self._show_step_archivo()

        self.update_idletasks()
        max_height = int(self.winfo_screenheight() * 0.8)
        self.minsize(760, 480)
        self.maxsize(1100, max_height)

        self.after(50, _center_dialog, self, parent)
        self.wait_visibility()
        self.grab_set()
        self.bind("<Escape>", lambda e: self.destroy())
        self.wait_window(self)

    def _load_existing_profile(self, prof: Profile) -> bool:
        """Prepara el wizard en modo edición: usa el archivo VIVO de la
        máquina (datos/<id>/actual.csv) como fuente y validación — es el que
        no se puede corromper — y salta directo al paso de campos, ya que la
        identidad y la orientación de una máquina existente no se editan acá
        (un cambio de orientación es, en la práctica, un archivo distinto:
        corresponde dar de alta una máquina nueva)."""
        self._machine_id = prof.id
        self.var_id = tk.StringVar(value=prof.id)
        self.var_nombre = tk.StringVar(value=prof.nombre)
        self.var_desc = tk.StringVar(value=prof.descripcion)
        self._orientacion.set(prof.orientacion)
        if prof.orientacion == "columnas":
            self._primera_col = prof.primera_columna_datos
        else:
            self._header_row = prof.fila_encabezado
            self._primera_fila_datos = prof.primera_fila_datos

        self._csv_path = os.path.join(paths.data_dir_for(prof.id), f"actual.{prof.extension}")
        try:
            self._info = profile_builder.sniff_csv(self._csv_path)
            self._grid = profile_builder.read_grid(self._csv_path, self._info["delimitador"])
        except (OSError, UnicodeDecodeError) as exc:
            Messagebox.show_error(f"No se pudo leer el archivo actual de la "
                                  f"máquina:\n\n{exc}", "Error", parent=self.master)
            return False
        if not self._grid or not any(self._grid):
            Messagebox.show_error("El archivo actual de la máquina está vacío.",
                                  "Error", parent=self.master)
            return False

        self._build_row_state_from_profile(prof)
        self._show_step_campos()
        return True

    def _clear(self) -> None:
        for c in self._content.winfo_children():
            c.destroy()

    # -- Paso 1: identidad + archivo -------------------------------------------
    def _show_step_archivo(self) -> None:
        self._header_label.config(text="Paso 1 de 4 — Máquina y archivo de muestra")
        self._clear()
        self.var_id = getattr(self, "var_id", tk.StringVar())
        self.var_nombre = getattr(self, "var_nombre", tk.StringVar())
        self.var_desc = getattr(self, "var_desc", tk.StringVar())

        footer = tk.Frame(self._content, bg=PANEL, padx=24)
        footer.pack(fill="x", side="bottom", pady=14)
        button(footer, "Cancelar", self.destroy, kind="secondary").pack(side="right")
        button(footer, "Continuar", self._on_step1_continue, kind="primary").pack(
            side="right", padx=(0, 10))

        _, body = build_scrollable_canvas(self, self._content)
        body.configure(padx=24, pady=16)
        body.columnconfigure(0, weight=1)

        def field_label(text):
            tk.Label(body, text=text, bg=PANEL, fg=TEXT, font=FONT_BOLD,
                     anchor="w").pack(fill="x", pady=(4, 2))

        def hint_label(text):
            tk.Label(body, text=text, bg=PANEL, fg=MUTED, font=FONT_SMALL,
                     anchor="w").pack(fill="x", pady=(0, 8))

        field_label("ID de la máquina")
        tb.Entry(body, textvariable=self.var_id, font=FONT,
                bootstyle="success").pack(fill="x", ipady=4)
        hint_label("código corto, ej. 233 (identifica su carpeta de datos)")

        field_label("Nombre")
        tb.Entry(body, textvariable=self.var_nombre, font=FONT,
                bootstyle="success").pack(fill="x", ipady=4, pady=(0, 8))

        field_label("Descripción (opcional)")
        tb.Entry(body, textvariable=self.var_desc, font=FONT,
                bootstyle="success").pack(fill="x", ipady=4, pady=(0, 8))

        field_label("Archivo CSV de muestra")
        file_row = tk.Frame(body, bg=PANEL)
        file_row.pack(fill="x", pady=(0, 4))
        self._file_label = tk.Label(file_row, text="(ningún archivo elegido)",
                                    bg=PANEL, fg=MUTED, font=FONT_SMALL, anchor="w")
        self._file_label.pack(side="left", fill="x", expand=True)
        button(file_row, "Adjuntar…", self._pick_file, kind="secondary",
              small=True).pack(side="right")
        tk.Label(body, bg=PANEL, fg=MUTED, font=FONT_SMALL, anchor="w",
                 justify="left", wraplength=760,
                 text="En los próximos pasos vas a poder elegir vos qué filas o "
                      "columnas del archivo son campos editables (con nombre y "
                      "tipo de dato propios). Todo lo que no elijas se conserva "
                      "igual, oculto, para no perder ningún dato del archivo "
                      "original.").pack(fill="x", pady=(10, 0))


    def _pick_file(self) -> None:
        path = filedialog.askopenfilename(
            title="Elegir CSV de la máquina nueva",
            filetypes=[("CSV", "*.csv"), ("Todos los archivos", "*.*")])
        if path:
            self._csv_path = path
            self._file_label.config(text=os.path.basename(path), fg=TEXT)

    def _on_step1_continue(self) -> None:
        raw_id = self.var_id.get().strip()
        if not raw_id:
            warn(self, "Falta el ID", "Ingresá un ID corto para la máquina.")
            return
        machine_id = re.sub(r"[^a-zA-Z0-9_-]+", "_", raw_id).strip("_")
        if not machine_id:
            warn(self, "ID inválido", "El ID debe tener letras o números.")
            return
        if machine_id in self.existing_ids:
            warn(self, "ID repetido", f"Ya existe una máquina con ID «{machine_id}».")
            return
        if not self._csv_path:
            warn(self, "Falta el archivo", "Adjuntá el CSV de la máquina nueva.")
            return
        self._machine_id = machine_id

        try:
            self._info = profile_builder.sniff_csv(self._csv_path)
            self._grid = profile_builder.read_grid(self._csv_path, self._info["delimitador"])
        except (OSError, UnicodeDecodeError) as exc:
            error(self, "No se pudo leer el archivo", str(exc))
            return
        if not self._grid or not any(self._grid):
            error(self, "Archivo vacío", "El CSV está vacío o no se pudo leer.")
            return

        self._show_step_orientacion()

    # -- Paso 2: orientación -----------------------------------------------
    def _show_step_orientacion(self) -> None:
        self._header_label.config(text="Paso 2 de 4 — ¿Cómo está organizado el CSV?")
        self._clear()

        footer = tk.Frame(self._content, bg=PANEL, padx=24)
        footer.pack(fill="x", side="bottom", pady=14)
        button(footer, "Cancelar", self.destroy, kind="secondary").pack(side="right")
        button(footer, "Continuar", self._on_step2_continue, kind="primary").pack(
            side="right", padx=(0, 10))
        button(footer, "Atrás", self._show_step_archivo, kind="secondary").pack(side="left")

        _, body = build_scrollable_canvas(self, self._content)
        body.configure(padx=24, pady=16)

        tb.Radiobutton(body, text="Cada fila es una pieza (CSV normal, con encabezado)",
                       variable=self._orientacion, value="filas",
                       bootstyle="success").pack(fill="x", anchor="w", pady=4)
        tb.Radiobutton(body, text="Cada columna es una pieza (formato transpuesto, "
                                   "como la 232)",
                       variable=self._orientacion, value="columnas",
                       bootstyle="success").pack(fill="x", anchor="w", pady=4)

        tk.Label(body, text="Vista previa (primeras filas/columnas crudas):",
                 bg=PANEL, fg=TEXT, font=FONT_BOLD, anchor="w").pack(
            fill="x", pady=(14, 4))
        preview = tk.Text(body, height=10, font=("Consolas", 9), bg=WHITE, fg=TEXT,
                          wrap="none", relief="solid", borderwidth=1)
        preview.pack(fill="both", expand=True)
        delim = self._info["delimitador"]
        for row in self._grid[:12]:
            texto = delim.join(row[:10])
            preview.insert("end", texto[:200] + ("…\n" if len(texto) > 200 else "\n"))
        preview.config(state="disabled")

    def _on_step2_continue(self) -> None:
        self._build_row_state()
        self._show_step_campos()

    # -- Preparar el estado por fila/columna (usado en el paso 3) --------------
    def _ejes(self):
        """Itera (idx, etiqueta, muestra_de_valores) sobre el eje "campo"
        del archivo: filas si orientacion='columnas', columnas si
        orientacion='filas'."""
        grid = self._grid
        if self._orientacion.get() == "columnas":
            primera = self._primera_col
            for r, row in enumerate(grid):
                etiqueta = (row[0] if row else "").strip()
                muestra = [v for v in row[primera:primera + 20] if v != ""][:5]
                yield r, etiqueta, muestra
        else:
            header = grid[self._header_row] if len(grid) > self._header_row else []
            muestras = grid[self._primera_fila_datos:self._primera_fila_datos + 20]
            for i, h in enumerate(header):
                etiqueta = (h or "").strip()
                vals = [row[i] for row in muestras if i < len(row) and row[i] != ""][:5]
                yield i, etiqueta, vals

    def _build_row_state(self) -> None:
        self._row_state = {}
        primera_col = self._primera_col
        es_columnas = self._orientacion.get() == "columnas"

        clave_sugerida = None
        if es_columnas:
            clave_sugerida = profile_builder.suggest_clave_row(self._grid, primera_col)
        if clave_sugerida is None:
            clave_sugerida = 0
        self._clave_idx.set(str(clave_sugerida))

        for idx, etiqueta, muestra in self._ejes():
            if es_columnas:
                kind = profile_builder.classify_row(self._grid, idx, primera_col)
                if kind == "fija" and idx > clave_sugerida:
                    # Ver profile_builder.build_profile_columnas: una fila
                    # después de la clave nunca se sugiere "fija" (podría
                    # ser un parámetro por pieza hoy constante), para no
                    # arriesgar el ancho de la fila al agregar/borrar.
                    kind = "dato"
            else:
                kind = "dato"
            sug = profile_builder.suggest_tipo(muestra, self._info.get("simbolo_decimal"))
            incluir_default = (idx == clave_sugerida) or (kind == "dato" and idx != clave_sugerida)
            st = {
                "kind": kind,
                "etiqueta": etiqueta,
                "muestra": muestra,
                "incluir": tk.BooleanVar(value=incluir_default),
                "nombre": tk.StringVar(value=self._slug_preview(etiqueta, idx)),
                "titulo": tk.StringVar(value=etiqueta or f"Campo {idx + 1}"),
                "tipo": tk.StringVar(value=sug["tipo"]),
                "ancho": tk.StringVar(value=str(sug["formato"].get("ancho", ""))),
                "decimales": tk.StringVar(value=str(sug["formato"].get("decimales", ""))),
                "separador": tk.StringVar(value=sug["formato"].get("separador_decimal", ",")),
                "kind_override": tk.StringVar(value=self._kind_to_override(kind)),
                "_min": None, "_max": None, "_default": None,
            }
            self._row_state[idx] = st

    def _build_row_state_from_profile(self, prof: Profile) -> None:
        """Igual que `_build_row_state`, pero parte de un perfil YA
        existente en vez de autodetectar todo: cada fila/columna del
        archivo se prellena con el campo/fila-fija/fila-índice que ya
        tiene declarado. Filas que el archivo vivo tenga de más respecto al
        perfil (p. ej. si el CSV en planta creció) se autodetectan igual
        que en el alta, para no dejarlas fuera."""
        self._row_state = {}
        es_columnas = self._orientacion.get() == "columnas"

        if es_columnas:
            campo_por_idx = {c.fila: c for c in prof.campos}
            fija_por_idx = {ff["fila"]: ff for ff in prof.filas_fijas}
            indice_idx = prof.fila_indice["fila"] if prof.fila_indice else None
        else:
            campo_por_idx = {c.columna: c for c in prof.campos}
            fija_por_idx = {}
            indice_idx = None

        clave = prof.campo_clave()
        clave_idx = clave.fila if es_columnas else clave.columna
        self._clave_idx.set(str(clave_idx))
        self._clave_idx_original = clave_idx

        for idx, etiqueta, muestra in self._ejes():
            min_default = max_default = default_default = None
            if idx in campo_por_idx:
                c = campo_por_idx[idx]
                kind = "campo"
                incluir_default = c.visible
                nombre_default, titulo_default = c.nombre_interno, c.titulo_ui
                tipo_default, formato = c.tipo, dict(c.formato or {})
                min_default, max_default, default_default = c.min, c.max, c.default
                if tipo_default in ("entero_ceros", "decimal") and not formato:
                    # Perfil viejo sin 'formato' explícito (p. ej. dado de
                    # alta antes de este esquema): sugerir uno a partir de
                    # una muestra real para no perder precisión/ceros la
                    # primera vez que se edite ese campo. Si la muestra no
                    # coincide con el tipo ya declarado, se deja vacío (el
                    # usuario lo completa a mano).
                    sug = profile_builder.suggest_tipo(muestra, self._info.get("simbolo_decimal"))
                    if sug["tipo"] == tipo_default:
                        formato = sug["formato"]
            elif idx in fija_por_idx:
                kind = "fija"
                incluir_default = False
                nombre_default = self._slug_preview(etiqueta, idx)
                titulo_default = etiqueta or f"Campo {idx + 1}"
                tipo_default, formato = "texto", {}
            elif idx == indice_idx:
                kind = "indice"
                incluir_default = False
                nombre_default = self._slug_preview(etiqueta, idx)
                titulo_default = etiqueta or f"Campo {idx + 1}"
                tipo_default, formato = "texto", {}
            else:
                # Fila/columna que el archivo vivo tiene de más respecto al
                # perfil guardado: se ofrece autodetectada, sin forzar nada.
                sug = profile_builder.suggest_tipo(muestra, self._info.get("simbolo_decimal"))
                kind = "dato"
                incluir_default = False
                nombre_default = self._slug_preview(etiqueta, idx)
                titulo_default = etiqueta or f"Campo {idx + 1}"
                tipo_default, formato = sug["tipo"], sug["formato"]

            st = {
                "kind": kind,
                "etiqueta": etiqueta,
                "muestra": muestra,
                "incluir": tk.BooleanVar(value=incluir_default),
                "nombre": tk.StringVar(value=nombre_default),
                "titulo": tk.StringVar(value=titulo_default),
                "tipo": tk.StringVar(value=tipo_default),
                "ancho": tk.StringVar(value=str(formato.get("ancho", ""))),
                "decimales": tk.StringVar(value=str(formato.get("decimales", ""))),
                "separador": tk.StringVar(value=formato.get("separador_decimal", ",")),
                "kind_override": tk.StringVar(value=self._kind_to_override(kind)),
                "_min": min_default, "_max": max_default, "_default": default_default,
            }
            self._row_state[idx] = st

    @staticmethod
    def _kind_to_override(kind: str) -> str:
        return kind if kind in ("fija", "indice") else "oculto"

    @staticmethod
    def _slug_preview(etiqueta: str, idx: int) -> str:
        s = re.sub(r"[^a-zA-Z0-9]+", "_", (etiqueta or "").strip().lower()).strip("_")
        return s or f"campo_{idx}"

    # -- Paso 3: tabla de campos (selección indefinida + tipo) -----------------
    KIND_OVERRIDE_LABELS = [("oculto", "oculto"), ("fija", "fila fija"),
                            ("indice", "fila índice")]

    def _show_step_campos(self) -> None:
        titulo_paso = "Elegí los campos" if not self._edit_mode else "Ajustá los campos"
        self._header_label.config(
            text=(f"{titulo_paso}" if self._edit_mode
                  else f"Paso 3 de 4 — {titulo_paso}"))
        self._clear()

        info_row = tk.Frame(self._content, bg=PANEL, padx=18)
        info_row.pack(fill="x", pady=(10, 4))
        if self._edit_mode:
            texto_info = (f"Editando «{self._existing_profile.nombre}» (ID "
                          f"{self._existing_profile.id}). Los valores de abajo son "
                          "los que ya tiene esta máquina configurados. Podés "
                          "renombrar campos, cambiar su tipo/formato, mostrar "
                          "campos ocultos o esconder alguno — mientras no toques "
                          "celdas ya guardadas, no se pierde ningún dato.")
        else:
            texto_info = ("Marcá ● junto a la fila/columna que es el CÓDIGO de "
                          "cada pieza, y tildá ☑ las que querés administrar como "
                          "campos (nombre, título y tipo editables). Para lo que "
                          "dejes sin tildar, elegí si se guarda oculto (viaja con "
                          "cada pieza), como fila fija (constante) o como fila "
                          "índice (se renumera sola).")
        tk.Label(info_row, bg=PANEL, fg=MUTED, font=FONT_SMALL, anchor="w",
                 justify="left", wraplength=800, text=texto_info).pack(fill="x")

        wrap = tk.Frame(self._content, bg=PANEL, padx=18)
        wrap.pack(fill="both", expand=True)
        canvas, table = build_scrollable_canvas(self, wrap, h_scroll=True)

        headers = ["Clave", "Incluir", "Etiqueta detectada", "Nombre interno",
                   "Título en la tabla", "Tipo", "Formato", "Si no es campo", "Muestra"]
        for col, h in enumerate(headers):
            tk.Label(table, text=h, bg=PANEL, fg=MUTED, font=FONT_SMALL,
                     anchor="w").grid(row=0, column=col, sticky="w", padx=4, pady=(0, 4))

        es_columnas = self._orientacion.get() == "columnas"
        badge_txt = {"fija": "fija", "indice": "índice", "campo": "existente"}

        for r, (idx, st) in enumerate(sorted(self._row_state.items()), start=1):
            tb.Radiobutton(table, variable=self._clave_idx, value=str(idx),
                          bootstyle="success").grid(row=r, column=0, padx=4)
            chk = tb.Checkbutton(table, variable=st["incluir"], bootstyle="success")
            chk.grid(row=r, column=1, padx=4)
            badge = badge_txt.get(st["kind"], "")
            tk.Label(table, text=(st["etiqueta"][:28] or "—") +
                          (f"  [{badge}]" if badge else ""),
                     bg=PANEL, fg=TEXT, font=FONT_SMALL, anchor="w").grid(
                row=r, column=2, sticky="w", padx=4)
            tb.Entry(table, textvariable=st["nombre"], font=FONT_SMALL, width=16,
                    bootstyle="success").grid(row=r, column=3, padx=4)
            tb.Entry(table, textvariable=st["titulo"], font=FONT_SMALL, width=18,
                    bootstyle="success").grid(row=r, column=4, padx=4)
            combo = tb.Combobox(table, textvariable=self._tipo_display_var(st),
                                values=[label for _, label in TIPOS_UI],
                                state="readonly", font=FONT_SMALL, width=22,
                                bootstyle="success")
            combo.grid(row=r, column=5, padx=4)
            extra = tk.Frame(table, bg=PANEL)
            extra.grid(row=r, column=6, padx=4, sticky="w")
            self._build_extra_widgets(extra, st)
            combo.bind("<<ComboboxSelected>>",
                      lambda e, c=combo, s=st, ex=extra: self._on_tipo_changed(c, s, ex))

            if es_columnas:
                kind_combo = tb.Combobox(
                    table, textvariable=self._kind_override_display_var(st),
                    values=[label for _, label in self.KIND_OVERRIDE_LABELS],
                    state="readonly", font=FONT_SMALL, width=11, bootstyle="secondary")
                kind_combo.grid(row=r, column=7, padx=4)
                self._sync_kind_override_state(kind_combo, st)
                st["incluir"].trace_add(
                    "write", lambda *a, c=kind_combo, s=st: self._sync_kind_override_state(c, s))
            else:
                tk.Label(table, text="oculto", bg=PANEL, fg=MUTED,
                         font=FONT_SMALL).grid(row=r, column=7, padx=4)

            tk.Label(table, text=" | ".join(st["muestra"])[:40], bg=PANEL, fg=MUTED,
                     font=FONT_SMALL, anchor="w").grid(row=r, column=8, sticky="w", padx=4)

        footer = tk.Frame(self._content, bg=PANEL, padx=18)
        footer.pack(fill="x", side="bottom", pady=14)
        button(footer, "Cancelar", self.destroy, kind="secondary").pack(side="right")
        button(footer, "Continuar", self._on_step3_continue, kind="primary").pack(
            side="right", padx=(0, 10))
        if not self._edit_mode:
            button(footer, "Atrás", self._show_step_orientacion,
                  kind="secondary").pack(side="left")

    def _kind_override_display_var(self, st: dict) -> tk.StringVar:
        labels = dict(self.KIND_OVERRIDE_LABELS)
        var = tk.StringVar(value=labels.get(st["kind_override"].get(), "oculto"))
        st["_kind_override_display"] = var

        def _sync(*_a):
            inv = {v: k for k, v in self.KIND_OVERRIDE_LABELS}
            st["kind_override"].set(inv.get(var.get(), "oculto"))
        var.trace_add("write", _sync)
        return var

    @staticmethod
    def _sync_kind_override_state(combo: tb.Combobox, st: dict) -> None:
        combo.config(state="disabled" if st["incluir"].get() else "readonly")

    def _tipo_display_var(self, st: dict) -> tk.StringVar:
        # Combobox trabaja con la etiqueta legible; se sincroniza con
        # st["tipo"] (el valor interno) al construir y al cambiar selección.
        var = tk.StringVar(value=TIPO_LABEL.get(st["tipo"].get(), "Texto"))
        st["_tipo_display"] = var
        return var

    def _build_extra_widgets(self, extra: tk.Frame, st: dict) -> None:
        tipo = st["tipo"].get()
        for w in extra.winfo_children():
            w.destroy()
        if tipo == "entero_ceros":
            tk.Label(extra, text="ancho:", bg=PANEL, fg=MUTED, font=FONT_SMALL).pack(side="left")
            tb.Entry(extra, textvariable=st["ancho"], width=4, font=FONT_SMALL,
                    bootstyle="success").pack(side="left", padx=(2, 0))
        elif tipo == "decimal":
            tk.Label(extra, text="decimales:", bg=PANEL, fg=MUTED, font=FONT_SMALL).pack(side="left")
            tb.Entry(extra, textvariable=st["decimales"], width=4, font=FONT_SMALL,
                    bootstyle="success").pack(side="left", padx=(2, 6))
            tk.Label(extra, text="sep.:", bg=PANEL, fg=MUTED, font=FONT_SMALL).pack(side="left")
            tb.Entry(extra, textvariable=st["separador"], width=2, font=FONT_SMALL,
                    bootstyle="success").pack(side="left", padx=(2, 0))

    def _on_tipo_changed(self, combo, st: dict, extra: tk.Frame) -> None:
        label = st["_tipo_display"].get()
        st["tipo"].set(TIPO_POR_LABEL.get(label, "texto"))
        self._build_extra_widgets(extra, st)

    def _remapped_features(self) -> dict:
        """En modo edición, preserva 'features' (placeholder/duplicados) del
        perfil existente — si no se propagan, editar el formato de una
        máquina apaga en silencio la detección de duplicados y de slots
        vacíos. Si además se renombró el campo clave, actualiza la
        referencia 'duplicados.campo' para que no quede apuntando a un
        nombre que ya no existe."""
        if not self._edit_mode:
            return {}
        features = json.loads(json.dumps(self._existing_profile.features or {}))
        dup = features.get("duplicados")
        if dup and dup.get("campo") == self._existing_profile.campo_clave().nombre_interno:
            clave_idx = int(self._clave_idx.get())
            nueva_clave = self._row_state[clave_idx]["nombre"].get().strip().lower()
            nueva_clave = re.sub(r"[^a-zA-Z0-9_]+", "_", nueva_clave).strip("_")
            if nueva_clave:
                dup["campo"] = nueva_clave
        return features

    def _on_step3_continue(self) -> None:
        try:
            clave_idx = int(self._clave_idx.get())
        except ValueError:
            warn(self, "Falta la clave", "Marcá cuál fila/columna es el código.")
            return
        self._clave_changed = (self._edit_mode and
                               clave_idx != self._clave_idx_original)

        nombres_usados: set[str] = set()
        campos_elegidos = []
        row_kinds: dict[int, str] = {}
        es_columnas = self._orientacion.get() == "columnas"
        for idx, st in self._row_state.items():
            if idx == clave_idx:
                # La clave siempre es un campo (tipo texto fijo), pero su
                # nombre_interno/título SÍ vienen de lo que el usuario puso
                # en la tabla — si no se agrega acá, build_profile_* los
                # vuelve a derivar de la etiqueta cruda y pisa un nombre
                # elegido a propósito (p. ej. "code").
                nombre_clave = re.sub(r"[^a-zA-Z0-9_]+", "_",
                                      st["nombre"].get().strip().lower()).strip("_")
                if nombre_clave:
                    nombres_usados.add(nombre_clave)
                    campos_elegidos.append({
                        "fila" if es_columnas else "columna": idx,
                        "nombre_interno": nombre_clave,
                        "titulo_ui": st["titulo"].get().strip() or st["etiqueta"],
                    })
                continue
            if not st["incluir"].get():
                if es_columnas:
                    row_kinds[idx] = st["kind_override"].get()
                continue
            nombre = re.sub(r"[^a-zA-Z0-9_]+", "_", st["nombre"].get().strip().lower()).strip("_")
            if not nombre:
                warn(self, "Falta un nombre",
                    f"Ponele un nombre interno a «{st['titulo'].get() or st['etiqueta']}».")
                return
            if nombre in nombres_usados:
                warn(self, "Nombre repetido", f"El nombre interno «{nombre}» está repetido.")
                return
            nombres_usados.add(nombre)

            tipo = st["tipo"].get()
            formato = {}
            if tipo == "entero_ceros":
                try:
                    formato["ancho"] = max(1, int(st["ancho"].get() or 1))
                except ValueError:
                    warn(self, "Valor inválido",
                        f"«{st['titulo'].get()}»: el ancho de ceros debe ser un número entero.")
                    return
            elif tipo == "decimal":
                try:
                    formato["decimales"] = max(0, int(st["decimales"].get() or 0))
                except ValueError:
                    warn(self, "Valor inválido",
                        f"«{st['titulo'].get()}»: la cantidad de decimales debe ser un número entero.")
                    return
                formato["separador_decimal"] = st["separador"].get().strip() or ","

            key = "fila" if self._orientacion.get() == "columnas" else "columna"
            campos_elegidos.append({
                key: idx, "nombre_interno": nombre,
                "titulo_ui": st["titulo"].get().strip() or st["etiqueta"] or nombre,
                "tipo": tipo, "formato": formato,
                "min": st.get("_min"), "max": st.get("_max"), "default": st.get("_default"),
            })

        machine_id = self._machine_id
        nombre_maquina = self.var_nombre.get().strip() or f"Máquina {machine_id}"
        desc = self.var_desc.get().strip()
        archivo_inicial = (self._existing_profile.archivo_inicial if self._edit_mode
                          else os.path.basename(self._csv_path))
        features = self._remapped_features()

        try:
            if es_columnas:
                self._perfil_dict = profile_builder.build_profile_columnas(
                    machine_id, nombre_maquina, desc, archivo_inicial, self._info,
                    self._grid, primera_col=self._primera_col, clave_row=clave_idx,
                    campos_elegidos=campos_elegidos, row_kinds=row_kinds,
                    features=features)
            else:
                self._perfil_dict = profile_builder.build_profile_filas(
                    machine_id, nombre_maquina, desc, archivo_inicial, self._info,
                    self._grid, header_row=self._header_row,
                    primera_fila_datos=self._primera_fila_datos,
                    clave_col=clave_idx, campos_elegidos=campos_elegidos,
                    features=features)
        except (ValueError, ProfileError) as exc:
            error(self, "No se pudo generar el perfil", str(exc))
            return

        self._show_step_validar()

    # -- Paso 4: validar byte-perfecto + confirmar ------------------------------
    def _show_step_validar(self) -> None:
        self._header_label.config(
            text="Confirmar cambios" if self._edit_mode else "Paso 4 de 4 — Confirmar")
        self._clear()

        footer = tk.Frame(self._content, bg=PANEL, padx=24)
        footer.pack(fill="x", side="bottom", pady=14)
        button(footer, "Cancelar", self.destroy, kind="secondary").pack(side="right")
        texto_confirmar = "Guardar cambios" if self._edit_mode else "Confirmar y guardar máquina"
        confirm_btn = button(footer, texto_confirmar, self._on_confirm, kind="primary")
        confirm_btn.pack(side="right", padx=(0, 10))
        button(footer, "Atrás", self._show_step_campos, kind="secondary").pack(side="left")

        _, body = build_scrollable_canvas(self, self._content)
        body.configure(padx=24, pady=16)

        try:
            prof = Profile.from_dict(self._perfil_dict)
            store = DataStore.load(self._csv_path, prof)
            with open(self._csv_path, "rb") as f:
                original = f.read()
            regenerado = store.to_text().encode(prof.encoding)
            ok = original == regenerado
            n_registros = len(store.records)
        except (ValueError, ProfileError, OSError, UnicodeDecodeError) as exc:
            ok = False
            n_registros = 0
            original = regenerado = b""
            error_msg = str(exc)
        else:
            error_msg = None

        n_visibles = len(prof.campos_visibles()) if error_msg is None else 0
        n_ocultos = (len(self._perfil_dict["campos"]) - n_visibles) if error_msg is None else 0

        resumen = (f"• {n_registros} registro(s) detectados\n"
                   f"• {n_visibles} campo(s) visible(s)\n"
                   f"• {n_ocultos} campo(s) oculto(s) (preservados, no editables)\n")
        tk.Label(body, text=resumen, bg=PANEL, fg=TEXT, font=FONT, justify="left",
                 anchor="w").pack(fill="x", pady=(0, 12))

        if error_msg:
            tk.Label(body, text=f"⚠ No se pudo validar el perfil:\n\n{error_msg}",
                     bg=PANEL, fg=RED_DARK, font=FONT, justify="left", wraplength=760,
                     anchor="w").pack(fill="x")
        elif ok:
            tk.Label(body, text="✅ Round-trip byte-perfecto: al reconstruir el "
                                 "archivo con este perfil se obtienen bytes "
                                 "IDÉNTICOS al original.",
                     bg=PANEL, fg=GREEN_DARK, font=FONT_BOLD, justify="left",
                     wraplength=760, anchor="w").pack(fill="x")
        else:
            primer_diff = None
            for i, (a, b) in enumerate(zip(original, regenerado)):
                if a != b:
                    primer_diff = i
                    break
            detalle = (f"primer byte distinto en la posición {primer_diff}"
                       if primer_diff is not None
                       else f"longitudes distintas ({len(original)} vs {len(regenerado)} bytes)")
            tk.Label(body, text="⚠ El perfil generado NO reconstruye el archivo "
                                 f"byte a byte ({detalle}). Volvé al paso anterior y "
                                 "revisá el tipo/formato de los campos marcados, o "
                                 "marcá como campo alguna fila/columna que hoy esté "
                                 "oculta.",
                     bg=PANEL, fg=RED_DARK, font=FONT, justify="left", wraplength=760,
                     anchor="w").pack(fill="x")

        self._validation_ok = (error_msg is None and ok)
        if not self._validation_ok:
            confirm_btn.config(state="disabled")

        if self._validation_ok and self._clave_changed:
            tk.Label(body, text="⚠ Cambiaste cuál fila/columna es el código de "
                                 "cada pieza. Las marcas guardadas hoy (por "
                                 "ejemplo, \"no es duplicado\" en el revisor de "
                                 "duplicados) están asociadas al código VIEJO y "
                                 "van a quedar sin efecto. Se te va a pedir "
                                 "confirmación antes de guardar.",
                     bg=PANEL, fg=AMBER, font=FONT, justify="left", wraplength=760,
                     anchor="w").pack(fill="x", pady=(12, 0))

    def _on_confirm(self) -> None:
        if not self._validation_ok:
            return

        if self._clave_changed:
            if not confirm(self, "Cambiar el código de la máquina",
                           "Elegiste una fila/columna distinta como código de "
                           "cada pieza. Las marcas guardadas hoy (por ejemplo, "
                           "\"no es duplicado\") quedan asociadas al código "
                           "VIEJO y van a dejar de aplicar.\n\n"
                           "¿Confirmás el cambio igual?"):
                return

        if self._edit_mode:
            profile_path = self._existing_profile.ruta
            try:
                backup_path = f"{profile_path}.bak-{datetime.now():%Y%m%d-%H%M%S}"
                shutil.copyfile(profile_path, backup_path)
                escribir_atomico(profile_path,
                                  json.dumps(self._perfil_dict, ensure_ascii=False, indent=2),
                                  encoding="utf-8")
                new_profile = Profile.from_dict(self._perfil_dict)
                new_profile.ruta = profile_path
            except (OSError, ProfileError) as exc:
                error(self, "Error al guardar los cambios", str(exc))
                return
            self.new_profile = new_profile
            self.destroy()
            return

        machine_id = self._perfil_dict["id"]
        profile_path = os.path.join(paths.profiles_dir(), f"maquina_{machine_id}.json")
        if os.path.exists(profile_path):
            warn(self, "Ya existe", f"Ya existe un perfil para «{machine_id}».")
            return
        try:
            escribir_atomico(profile_path,
                              json.dumps(self._perfil_dict, ensure_ascii=False, indent=2),
                              encoding="utf-8")
            new_profile = Profile.from_dict(self._perfil_dict)
            new_profile.ruta = profile_path
            data_dir = paths.data_dir_for(machine_id)
            ext = new_profile.extension
            copiar_atomico(self._csv_path, os.path.join(data_dir, f"original.{ext}"))
            copiar_atomico(self._csv_path, os.path.join(data_dir, f"actual.{ext}"))
        except (OSError, ProfileError) as exc:
            error(self, "Error al crear la máquina", str(exc))
            return

        self.new_profile = new_profile
        self.destroy()


# ============================================================================
#  Diálogo de alta / edición (campos dinámicos según el perfil)
# ============================================================================
class RecordDialog(tk.Toplevel):
    def __init__(self, parent, store: DataStore, title: str,
                 record: dict | None = None, edit_index: int | None = None):
        super().__init__(parent)
        self.store = store
        self.profile = store.profile
        self.edit_index = edit_index
        self.result: dict | None = None

        self.title(title)
        self.configure(bg=PANEL)
        self.resizable(True, True)
        self.transient(parent)

        self.vars: dict[str, tk.StringVar] = {}
        self.entries: dict[str, tk.Widget] = {}
        for campo in self.profile.campos_visibles():
            if record is not None:
                val = record.get(campo.nombre_interno, "")
            elif campo.default is not None:
                val = campo.default
            else:
                val = "" if campo.tipo == "texto" else 0
            self.vars[campo.nombre_interno] = tk.StringVar(value=str(val))

        self._build(title)
        # Limitar altura máxima al 80% de la pantalla
        self.update_idletasks()
        max_height = int(self.winfo_screenheight() * 0.8)
        self.minsize(400, 200)
        self.maxsize(600, max_height)

        self.after(50, _center_dialog, self, parent)
        self.wait_visibility()
        self.grab_set()
        first = self.profile.campos_visibles()[0].nombre_interno
        self.entries[first].focus_set()
        self.bind("<Return>", lambda e: self._on_ok())
        self.bind("<Escape>", lambda e: self.destroy())
        self.wait_window(self)

    def _build(self, title: str) -> None:
        header = tk.Frame(self, bg=GREEN, height=52)
        header.pack(fill="x")
        header.pack_propagate(False)
        tk.Label(header, text=title, bg=GREEN, fg=WHITE,
                 font=("Segoe UI Semibold", 13)).pack(side="left", padx=18)

        # Body scrolleable para soportar muchos campos
        body_wrap = tk.Frame(self, bg=PANEL)
        body_wrap.pack(fill="both", expand=True)
        canvas, body = build_scrollable_canvas(self, body_wrap)
        body.columnconfigure(0, weight=1)

        for row, campo in enumerate(self.profile.campos_visibles()):
            tk.Label(body, text=campo.titulo_ui, bg=PANEL, fg=TEXT,
                     font=FONT_BOLD, anchor="w").grid(
                row=row * 2, column=0, sticky="w", pady=(8, 2), padx=(24, 0))
            var = self.vars[campo.nombre_interno]
            if campo.tipo == "entero" and campo.min is not None and campo.max is not None:
                widget = tb.Spinbox(body, from_=campo.min, to=campo.max,
                                    textvariable=var, font=FONT, width=30,
                                    bootstyle="success")
            else:
                widget = tb.Entry(body, textvariable=var, font=FONT, width=32,
                                  bootstyle="success")
            widget.grid(row=row * 2 + 1, column=0, sticky="we", ipady=4, padx=(24, 0), pady=(0, 16))
            self.entries[campo.nombre_interno] = widget
            hint = self._hint(campo)
            if hint:
                tk.Label(body, text=hint, bg=PANEL, fg=MUTED, font=FONT_SMALL,
                         anchor="w").grid(row=row * 2 + 1, column=1, sticky="w",
                                          padx=(10, 0))

        footer = tk.Frame(self, bg=PANEL)
        footer.pack(fill="x", padx=24, pady=(0, 18))
        button(footer, "Cancelar", self.destroy, kind="secondary").pack(side="right")
        button(footer, "Guardar", self._on_ok, kind="primary").pack(
            side="right", padx=(0, 10))

    @staticmethod
    def _hint(campo: Campo) -> str:
        if campo.es_clave:
            return "identificador único"
        if campo.min is not None and campo.max is not None:
            return f"{int(campo.min)} a {int(campo.max)}"
        if campo.tipo in ("entero", "decimal"):
            return "número"
        return ""

    def _on_ok(self) -> None:
        clave = self.profile.campo_clave()
        valores: dict = {}
        for campo in self.profile.campos_visibles():
            raw = self.vars[campo.nombre_interno].get().strip()
            if campo.es_clave:
                if not raw:
                    warn(self, "Revisá los datos",
                        f"«{campo.titulo_ui}» no puede estar vacío.")
                    return
                valores[campo.nombre_interno] = raw
            elif campo.es_numerico:
                if raw == "":
                    valores[campo.nombre_interno] = campo.default or 0
                    continue
                try:
                    num = float(raw.replace(",", ".")) if campo.tipo == "decimal" \
                        else int(round(float(raw)))
                except ValueError:
                    warn(self, "Revisá los datos",
                        f"«{campo.titulo_ui}» debe ser un número.")
                    return
                error_rango = validacion.validar_valor_numerico(campo, num)
                if error_rango:
                    warn(self, "Revisá los datos", error_rango)
                    return
                valores[campo.nombre_interno] = num
            else:
                valores[campo.nombre_interno] = raw

        key_val = valores[clave.nombre_interno]
        dup = self.store.find_key(key_val, exclude_index=self.edit_index)
        if dup != -1:
            warn(self, "Código duplicado",
                f"Ya existe un registro con {clave.titulo_ui} «{key_val}» "
                f"(posición {dup + 1}).")
            return
        self.result = valores
        self.destroy()


# ============================================================================
#  Diálogo de duplicados (feature-gated por el perfil)
# ============================================================================
class DuplicatesDialog(tk.Toplevel):
    def __init__(self, parent, store: DataStore, sidecar: Sidecar):
        super().__init__(parent)
        self.store = store
        self.profile = store.profile
        self.sidecar = sidecar
        self.deleted_any = False
        self.reviewed_any = False
        self.eliminados: list[dict] = []  # snapshots (para el historial)

        self.title("Posibles duplicados")
        self.configure(bg=PANEL)
        self.geometry("780x580")
        self.minsize(620, 380)
        self.transient(parent)

        excluded = sidecar.keys_with("no_duplicado")
        self.groups = store.find_similar_groups(excluded_keys=excluded)
        self._check_vars: dict[int, tk.BooleanVar] = {}
        self._row_widgets: dict[int, dict] = {}

        self._build()
        self.after(50, _center_dialog, self, parent)
        self.wait_visibility()
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
        tk.Label(self, bg=PANEL, fg=MUTED, font=FONT_SMALL, anchor="w",
                 justify="left",
                 text=(f"{n_groups} grupo(s) con {n_records} registro(s) con "
                       "códigos parecidos. Copiá el código para buscarlo en SAP; "
                       "marcá \"Eliminar\" si es duplicado real, o \"No es "
                       "duplicado\" para descartarlo de esta búsqueda."
                       if n_groups else
                       "No se encontraron códigos con posible duplicado.")).pack(
            fill="x", padx=18, pady=(10, 6))

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
        button(footer, "Cerrar", self.destroy, kind="secondary").pack(side="right")
        button(footer, "Eliminar seleccionados", self._on_apply, kind="danger").pack(
            side="right", padx=(0, 10))

    def _row_text(self, rec: dict) -> str:
        parts = [str(rec[self.profile.campo_clave().nombre_interno])]
        for c in self.profile.parametros_visibles():
            parts.append(f"{c.titulo_ui} {rec[c.nombre_interno]}")
        return "   ·   ".join(parts)

    def _build_row(self, card: tk.Frame, idx: int) -> None:
        rec = self.store.records[idx]
        code = self.store.key_of(rec)
        var = tk.BooleanVar(value=False)
        self._check_vars[idx] = var
        row = tk.Frame(card, bg=WHITE)
        row.pack(fill="x", padx=12, pady=2)

        chk = tb.Checkbutton(row, variable=var, bootstyle="success")
        chk.pack(side="left")
        lbl = tk.Label(row, text=self._row_text(rec), bg=WHITE, fg=TEXT,
                       font=FONT, anchor="w")
        lbl.pack(side="left", fill="x", expand=True)

        keep_btn = button(row, "No es duplicado",
                          lambda i=idx: self._mark_not_duplicate(i),
                          kind="outline", small=True,
                          tooltip="Marcar como revisado: no vuelve a aparecer "
                                  "en futuras búsquedas de duplicados.")
        keep_btn.pack(side="right", padx=(6, 0))
        copy_btn = button(row, "Copiar código", lambda c=code: self._copy_code(c),
                          kind="secondary", small=True,
                          tooltip="Copiar al portapapeles para buscarlo en SAP.")
        copy_btn.pack(side="right")
        self._row_widgets[idx] = {"label": lbl, "checkbox": chk,
                                  "keep_btn": keep_btn, "copy_btn": copy_btn}

    def _copy_code(self, code: str) -> None:
        self.clipboard_clear()
        self.clipboard_append(code)
        toast(self, f"Código «{code}» copiado al portapapeles.")

    def _mark_not_duplicate(self, idx: int) -> None:
        code = self.store.key_of(self.store.records[idx])
        self.sidecar.set(code, "no_duplicado", True)
        self.reviewed_any = True
        w = self._row_widgets[idx]
        self._check_vars[idx].set(False)
        w["checkbox"].config(state="disabled")
        w["keep_btn"].config(state="disabled", text="Marcado: no es duplicado")
        w["copy_btn"].config(state="disabled")
        w["label"].config(fg=MUTED)

    def _on_apply(self) -> None:
        selected = [i for i, v in self._check_vars.items() if v.get()]
        if not selected:
            info(self, "Sin selección", "No marcaste ningún registro para eliminar.")
            return
        codes = [self.store.key_of(self.store.records[i]) for i in selected]
        preview = ", ".join(codes[:6]) + (" …" if len(codes) > 6 else "")
        if not confirm(self, "Confirmar eliminación",
                       f"¿Eliminar {len(selected)} registro(s) marcados como "
                       f"duplicados?\n\n{preview}"):
            return
        for i in sorted(selected, reverse=True):
            self.eliminados.append(dict(self.store.records[i]))
            self.store.delete(i)
        self.deleted_any = True
        self.destroy()


# ============================================================================
#  Diálogo de importación desde Excel (mapeo dinámico a campos del perfil)
# ============================================================================
class ImportDialog(tk.Toplevel):
    def __init__(self, parent, store: DataStore, workbook, filename: str,
                data_dir: str | None = None):
        super().__init__(parent)
        self.store = store
        self.profile = store.profile
        self.workbook = workbook
        self.data_dir = data_dir
        self.applied_any = False
        self.applied_diffs: list[dict] = []
        self.applied_new: list[dict] = []
        self.applied_obsolete: list[dict] = []
        self.sheet: str | None = None
        self._headers: list[str] = []
        self._combo_vars: dict[str, tk.StringVar] = {}

        self.title(f"Importar cambios — {filename}")
        self.configure(bg=PANEL)
        self.geometry("720x600")
        self.minsize(580, 440)
        self.transient(parent)

        self._header_frame = tk.Frame(self, bg=GREEN, height=56)
        self._header_frame.pack(fill="x")
        self._header_frame.pack_propagate(False)
        self._header_label = tk.Label(self._header_frame, text="Importar cambios",
                                      bg=GREEN, fg=WHITE,
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

        self.after(50, _center_dialog, self, parent)
        self.wait_visibility()
        self.grab_set()
        self.bind("<Escape>", lambda e: self.destroy())
        self.wait_window(self)

    def _clear(self) -> None:
        for c in self._content.winfo_children():
            c.destroy()

    # -- paso hoja -------------------------------------------------------------
    def _show_sheet_step(self, sheets: list[str]) -> None:
        self._header_label.config(text="Elegí la hoja del Excel")
        self._clear()
        tk.Label(self._content, bg=PANEL, fg=MUTED, font=FONT_SMALL, anchor="w",
                 text="El archivo tiene varias hojas. Elegí la de los datos.").pack(
            fill="x", padx=18, pady=(14, 8))
        var = tk.StringVar(value=sheets[0])
        box = tk.Frame(self._content, bg=PANEL)
        box.pack(fill="x", padx=18)
        for s in sheets:
            tb.Radiobutton(box, text=s, variable=var, value=s,
                           bootstyle="success").pack(fill="x", pady=2, anchor="w")
        footer = tk.Frame(self._content, bg=PANEL, padx=18)
        footer.pack(fill="x", side="bottom", pady=14)
        button(footer, "Cancelar", self.destroy, kind="secondary").pack(side="right")
        button(footer, "Continuar", lambda: self._on_sheet(var.get()),
              kind="primary").pack(side="right", padx=(0, 10))

    def _on_sheet(self, sheet: str) -> None:
        self.sheet = sheet
        self._show_mapping_step()

    # -- paso mapeo ------------------------------------------------------------
    SKIP = "— no importar —"

    def _show_mapping_step(self) -> None:
        self._header_label.config(text="Mapear columnas")
        self._clear()
        self._headers = excel_import.read_headers(self.workbook, self.sheet)
        guess = excel_import.guess_mapping_generic(self._headers, self.profile.campos_visibles())
        # El mapeo recordado de la última importación (Nivel 4.6) tiene
        # prioridad sobre la sugerencia automática — si el usuario ya lo
        # confirmó una vez para esta máquina, es más confiable que adivinar
        # de nuevo por similitud de texto.
        if self.data_dir:
            mapeo_guardado = import_mapeos.cargar(self.data_dir)
            guess.update(import_mapeos.aplicar_a_headers(mapeo_guardado, self._headers))

        tk.Label(self._content, bg=PANEL, fg=MUTED, font=FONT_SMALL, anchor="w",
                 justify="left",
                 text="Indicá qué columna del Excel corresponde a cada dato. El "
                      "código es obligatorio; el resto es opcional — dejá "
                      "\"no importar\" en los datos que ese Excel no trae, y "
                      "no se van a tocar.").pack(fill="x", padx=18, pady=(14, 10))
        form = tk.Frame(self._content, bg=PANEL)
        form.pack(fill="x", padx=18)
        form.columnconfigure(1, weight=1)
        combo_values = [self.SKIP] + self._headers
        self._combo_vars = {}
        for row, campo in enumerate(self.profile.campos_visibles()):
            titulo = campo.titulo_ui + ("  (obligatorio)" if campo.es_clave else "")
            tk.Label(form, text=titulo, bg=PANEL, fg=TEXT, font=FONT_BOLD,
                     anchor="w").grid(row=row, column=0, sticky="w", pady=8, padx=(0, 12))
            var = tk.StringVar(value=self.SKIP)
            gi = guess.get(campo.nombre_interno)
            if gi is not None:
                var.set(self._headers[gi])
            self._combo_vars[campo.nombre_interno] = var
            tb.Combobox(form, textvariable=var, values=combo_values,
                       state="readonly", font=FONT, width=32,
                       bootstyle="success").grid(row=row, column=1, sticky="we", pady=8)

        self._build_preview()

        footer = tk.Frame(self._content, bg=PANEL, padx=18)
        footer.pack(fill="x", side="bottom", pady=14)
        button(footer, "Cancelar", self.destroy, kind="secondary").pack(side="right")
        button(footer, "Continuar", self._on_mapping, kind="primary").pack(
            side="right", padx=(0, 10))

    def _build_preview(self, n_filas: int = 3) -> None:
        """Vista previa de las primeras filas de datos crudas del archivo
        (todas las columnas, sin aplicar el mapeo), para confirmar a simple
        vista que la columna elegida en cada combo es la correcta antes de
        continuar (Nivel 4.6)."""
        hoja = self.workbook[self.sheet]
        filas = list(hoja.iter_rows(min_row=2, max_row=1 + n_filas, values_only=True))
        if not filas:
            return
        tk.Label(self._content, bg=PANEL, fg=MUTED, font=FONT_SMALL, anchor="w",
                 text=f"Vista previa (primeras {len(filas)} fila(s) del archivo):").pack(
            fill="x", padx=18, pady=(10, 4))
        wrap = tk.Frame(self._content, bg=BORDER, padx=1, pady=1)
        wrap.pack(fill="x", padx=18, pady=(0, 4))
        tree = tb.Treeview(wrap, columns=list(range(len(self._headers))),
                           show="headings", height=min(len(filas), n_filas),
                           bootstyle="success")
        for i, h in enumerate(self._headers):
            tree.heading(str(i), text=h)
            tree.column(str(i), width=110, anchor="w")
        for fila in filas:
            valores = [("" if v is None else v) for v in fila[:len(self._headers)]]
            tree.insert("", "end", values=valores)
        tree.pack(fill="x")

    def _on_mapping(self) -> None:
        clave_nombre = self.profile.campo_clave().nombre_interno
        chosen = {k: v.get() for k, v in self._combo_vars.items()}
        mapped = {k: v for k, v in chosen.items() if v and v != self.SKIP}

        if clave_nombre not in mapped:
            warn(self, "Falta la columna del código",
                f"Elegí qué columna del Excel es «{self.profile.campo_clave().titulo_ui}» "
                "— es obligatoria para poder comparar los registros.")
            return
        if len(mapped) == 1:
            warn(self, "Nada para comparar",
                "Además del código, mapeá al menos un dato (por ejemplo "
                "\"Gramos de Carga\") para poder detectar cambios.")
            return
        if len(set(mapped.values())) != len(mapped):
            warn(self, "Columnas repetidas", "Cada dato debe ir a una columna distinta.")
            return

        if self.data_dir:
            try:
                import_mapeos.guardar(self.data_dir, mapped)
            except OSError:
                pass  # recordar el mapeo es una comodidad, no debe bloquear la importación

        self._mapped_fields = set(mapped.keys())
        col_by_field = {k: self._headers.index(v) for k, v in mapped.items()}
        try:
            rows = excel_import.read_rows_generic(self.workbook, self.sheet, col_by_field)
        except Exception as exc:
            error(self, "Error al leer el Excel", str(exc))
            return
        self.diffs, self.new_records, self.obsolete, self.unchanged = \
            importacion.calcular_diferencias(
                self.store, self.profile, self._mapped_fields, rows)
        self._show_diff_step()

    # -- paso diff -------------------------------------------------------------
    def _show_diff_step(self) -> None:
        self._header_label.config(text="Revisar cambios")
        self._clear()
        n_invalidos = sum(1 for d in self.diffs if d["errores"]) + \
            sum(1 for d in self.new_records if d["errores"])
        partes = [f"{len(self.diffs)} con diferencias"]
        if self.unchanged:
            partes.append(f"{self.unchanged} sin cambios")
        if self.new_records:
            partes.append(f"{len(self.new_records)} código(s) nuevo(s)")
        if self.obsolete:
            partes.append(f"{len(self.obsolete)} código(s) no están en el Excel")
        tk.Label(self._content, bg=PANEL, fg=MUTED, font=FONT_SMALL, anchor="w",
                 text=" · ".join(partes)).pack(fill="x", padx=18, pady=(12, 4))
        if n_invalidos:
            tk.Label(self._content, bg=PANEL, fg=RED_DARK, font=FONT_BOLD, anchor="w",
                     text=f"⚠ {n_invalidos} valor(es) fuera de rango — no se pueden "
                          "importar hasta corregir el Excel (marcados en rojo abajo).").pack(
                fill="x", padx=18, pady=(0, 4))

        if not self.diffs and not self.new_records and not self.obsolete:
            tk.Label(self._content, bg=PANEL, fg=TEXT, font=FONT,
                     text="No hay cambios para revisar.").pack(padx=18, pady=20)
            footer = tk.Frame(self._content, bg=PANEL, padx=18)
            footer.pack(fill="x", side="bottom", pady=14)
            button(footer, "Cerrar", self.destroy, kind="primary").pack(side="right")
            return

        wrap = tk.Frame(self._content, bg=PANEL, padx=18)
        wrap.pack(fill="both", expand=True)
        canvas, inner = build_scrollable_canvas(self, wrap)
        params = [c for c in self.profile.parametros()
                 if c.nombre_interno in self._mapped_fields]
        campos_mapeados = [c for c in self.profile.campos_visibles()
                           if c.nombre_interno in self._mapped_fields]

        self._diff_vars: dict[int, tk.BooleanVar] = {}
        self._new_vars: dict[str, tk.BooleanVar] = {}
        self._obsolete_vars: dict[int, tk.BooleanVar] = {}

        if self.diffs:
            self._section_header(inner, "Modificaciones", GREEN_DARK,
                                 self._diff_vars, lambda: self.diffs)
            for d in self.diffs:
                invalido = bool(d["errores"])
                card = tk.Frame(inner, bg=WHITE, highlightthickness=1,
                                highlightbackground=(RED_DARK if invalido else BORDER))
                card.pack(fill="x", pady=(0, 10), padx=(0, 14))
                head = tk.Frame(card, bg=WHITE)
                head.pack(fill="x", padx=12, pady=(8, 2))
                var = tk.BooleanVar(value=False)
                self._diff_vars[d["idx"]] = var
                chk = tb.Checkbutton(head, variable=var, bootstyle="success")
                chk.pack(side="left")
                if invalido:
                    chk.config(state="disabled")
                title = d["code"]
                tk.Label(head, text=title, bg=WHITE,
                         fg=RED_DARK if invalido else GREEN_DARK, font=FONT_BOLD,
                         anchor="w").pack(side="left", fill="x", expand=True)

                for c in params:
                    old = d["old"][c.nombre_interno]
                    new = d["new"][c.nombre_interno]
                    r = tk.Frame(card, bg=WHITE)
                    r.pack(fill="x", padx=12, pady=1)
                    tk.Label(r, text=c.titulo_ui, bg=WHITE, fg=MUTED, font=FONT_SMALL,
                             width=18, anchor="w").pack(side="left")
                    if new is None:
                        txt, col = f"{old}  (sin dato en Excel, no se modifica)", MUTED
                    elif new != old:
                        txt, col = f"{old}  →  {new}", GREEN_DARK
                    else:
                        txt, col = f"{old}", TEXT
                    if c.nombre_interno in d.get("redondeos", []):
                        txt += "  ⚠ redondeado (el Excel traía decimales)"
                        col = AMBER
                    fnt = FONT_BOLD if (new is not None and new != old) else FONT
                    tk.Label(r, text=txt, bg=WHITE, fg=col, font=fnt,
                             anchor="w").pack(side="left")
                for err in d["errores"]:
                    tk.Label(card, text=f"⚠ {err.mensaje}", bg=WHITE, fg=RED_DARK,
                             font=FONT_SMALL, anchor="w", wraplength=560,
                             justify="left").pack(fill="x", padx=12, pady=(2, 0))
                tk.Frame(card, bg=WHITE, height=6).pack()

        if self.new_records:
            self._section_header(inner, "Códigos nuevos para agregar", AMBER,
                                 self._new_vars, lambda: self.new_records,
                                 key_fn=lambda d: d["code"])
            for d in self.new_records:
                invalido = bool(d["errores"])
                card = tk.Frame(inner, bg=WHITE, highlightthickness=1,
                                highlightbackground=(RED_DARK if invalido else BORDER))
                card.pack(fill="x", pady=(0, 10), padx=(0, 14))
                head = tk.Frame(card, bg=WHITE)
                head.pack(fill="x", padx=12, pady=(8, 2))
                var = tk.BooleanVar(value=False)
                self._new_vars[d["code"]] = var
                chk = tb.Checkbutton(head, variable=var, bootstyle="success")
                chk.pack(side="left")
                if invalido:
                    chk.config(state="disabled")
                tk.Label(head, text=d["code"], bg=WHITE,
                         fg=RED_DARK if invalido else AMBER, font=FONT_BOLD,
                         anchor="w").pack(side="left", fill="x", expand=True)

                for c in campos_mapeados:
                    if c.es_clave:
                        continue
                    val = d["valores"].get(c.nombre_interno)
                    r = tk.Frame(card, bg=WHITE)
                    r.pack(fill="x", padx=12, pady=1)
                    tk.Label(r, text=c.titulo_ui, bg=WHITE, fg=MUTED, font=FONT_SMALL,
                             width=18, anchor="w").pack(side="left")
                    txt = "(sin dato)" if val is None else str(val)
                    col = TEXT
                    if c.nombre_interno in d.get("redondeos", []):
                        txt += "  ⚠ redondeado (el Excel traía decimales)"
                        col = AMBER
                    tk.Label(r, text=txt, bg=WHITE, fg=col, font=FONT,
                             anchor="w").pack(side="left")
                for err in d["errores"]:
                    tk.Label(card, text=f"⚠ {err.mensaje}", bg=WHITE, fg=RED_DARK,
                             font=FONT_SMALL, anchor="w", wraplength=560,
                             justify="left").pack(fill="x", padx=12, pady=(2, 0))
                tk.Frame(card, bg=WHITE, height=6).pack()

        if self.obsolete:
            self._section_header(
                inner, "Códigos del catálogo que no están en el Excel", RED_DARK,
                self._obsolete_vars, lambda: self.obsolete)
            tk.Label(inner, bg=PANEL, fg=MUTED, font=FONT_SMALL, anchor="w",
                     wraplength=560, justify="left",
                     text="Marcá los que quieras eliminar del catálogo por estar "
                         "obsoletos. Los que dejes sin marcar se conservan tal "
                         "cual están.").pack(fill="x", padx=2, pady=(0, 6))
            for d in self.obsolete:
                row = tk.Frame(inner, bg=WHITE, highlightthickness=1,
                               highlightbackground=BORDER)
                row.pack(fill="x", pady=(0, 6), padx=(0, 14))
                var = tk.BooleanVar(value=False)
                self._obsolete_vars[d["idx"]] = var
                tb.Checkbutton(row, variable=var, bootstyle="danger").pack(
                    side="left", padx=(8, 4), pady=6)
                tk.Label(row, text=d["code"], bg=WHITE, fg=TEXT, font=FONT,
                         anchor="w").pack(side="left", fill="x", expand=True, pady=6)

        footer = tk.Frame(self._content, bg=PANEL, padx=18)
        footer.pack(fill="x", side="bottom", pady=14)
        button(footer, "Cerrar", self.destroy, kind="secondary").pack(side="right")
        button(footer, "Aplicar seleccionados", self._on_apply, kind="primary").pack(
            side="right", padx=(0, 10))

    def _section_header(self, parent, title: str, color: str,
                        vars_dict: dict, items_fn, key_fn=lambda d: d["idx"]) -> None:
        head = tk.Frame(parent, bg=PANEL)
        head.pack(fill="x", pady=(6, 6), padx=(0, 14))
        tk.Label(head, text=title, bg=PANEL, fg=color, font=FONT_BOLD,
                 anchor="w").pack(side="left")
        button(head, "Todos", lambda: self._set_all(vars_dict, items_fn(), key_fn, True),
              kind="ghost", small=True).pack(side="left", padx=(10, 0))
        button(head, "Ninguno", lambda: self._set_all(vars_dict, items_fn(), key_fn, False),
              kind="ghost", small=True).pack(side="left", padx=(2, 0))

    def _set_all(self, vars_dict: dict, items: list, key_fn, value: bool) -> None:
        for d in items:
            # Los inválidos (fuera de rango) nunca se marcan por "Todos": su
            # casilla ya está deshabilitada, forzarla igual sería confuso.
            if value and d.get("errores"):
                continue
            vars_dict[key_fn(d)].set(value)

    def _on_apply(self) -> None:
        # El filtro por "errores" es un refuerzo (belt-and-suspenders): la
        # casilla de un ítem inválido ya está deshabilitada en la UI, pero no
        # confiamos únicamente en eso para decidir qué se escribe al archivo
        # de la máquina.
        sel_diffs = [d for d in self.diffs
                    if self._diff_vars[d["idx"]].get() and not d["errores"]]
        sel_new = [d for d in self.new_records
                  if self._new_vars[d["code"]].get() and not d["errores"]]
        sel_obsolete = [d for d in self.obsolete if self._obsolete_vars[d["idx"]].get()]

        if not sel_diffs and not sel_new and not sel_obsolete:
            info(self, "Sin selección", "No marcaste ningún cambio para aplicar.")
            return

        partes = []
        if sel_diffs:
            partes.append(f"{len(sel_diffs)} modificación(es)")
        if sel_new:
            partes.append(f"{len(sel_new)} código(s) nuevo(s)")
        if sel_obsolete:
            partes.append(f"{len(sel_obsolete)} código(s) a eliminar")

        codes = [d["code"] for d in sel_diffs + sel_new + sel_obsolete]
        preview = ", ".join(codes[:6]) + (" …" if len(codes) > 6 else "")
        msg = f"¿Aplicar {', '.join(partes)}?"
        if sel_obsolete:
            msg += (f"\n\n¡Atención! Esto borra permanentemente "
                    f"{len(sel_obsolete)} registro(s) del catálogo.")
        msg += f"\n\n{preview}"
        if not confirm(self, "Confirmar importación", msg):
            return

        # Snapshots ANTES de mutar el store, para que el historial (app.py:
        # on_import) pueda registrar valores anteriores/nuevos reales.
        self.applied_diffs = [dict(d, old_completo=dict(self.store.records[d["idx"]]))
                              for d in sel_diffs]
        self.applied_new = list(sel_new)
        self.applied_obsolete = [dict(d, registro=dict(self.store.records[d["idx"]]))
                                 for d in sel_obsolete]

        for d in sel_diffs:
            cambios = {f: v for f, v in d["new"].items() if v is not None}
            self.store.update(d["idx"], cambios)
        for d in sel_new:
            self.store.add(self.store.nuevo_registro(d["valores"]))
        for idx in sorted((d["idx"] for d in sel_obsolete), reverse=True):
            self.store.delete(idx)

        self.applied_any = True
        self.destroy()


# ============================================================================
#  Diálogo de backups (Nivel 2.1 del plan de mejoras)
# ============================================================================
class BackupsDialog(tk.Toplevel):
    """Lista los puntos de respaldo automáticos (backups.py) y permite
    restaurar uno, con una vista previa de qué se perdería/recuperaría/
    cambiaría respecto del estado actual antes de confirmar."""

    def __init__(self, parent, data_dir: str, path_actual: str, profile: Profile,
                store: DataStore):
        super().__init__(parent)
        self.data_dir = data_dir
        self.path_actual = path_actual
        self.profile = profile
        self.store_actual = store
        self.restaurado = False

        self.title("Backups")
        self.configure(bg=PANEL)
        self.geometry("640x520")
        self.minsize(520, 380)
        self.transient(parent)

        self._build()
        self.after(50, _center_dialog, self, parent)
        self.wait_visibility()
        self.grab_set()
        self.bind("<Escape>", lambda e: self.destroy())
        self.wait_window(self)

    def _build(self) -> None:
        header = tk.Frame(self, bg=GREEN, height=56)
        header.pack(fill="x")
        header.pack_propagate(False)
        tk.Label(header, text="Puntos de respaldo automáticos", bg=GREEN, fg=WHITE,
                 font=("Segoe UI Semibold", 13)).pack(side="left", padx=18)

        lista = backups.listar_backups(self.data_dir)
        tk.Label(self, bg=PANEL, fg=MUTED, font=FONT_SMALL, anchor="w", justify="left",
                 text=(f"{len(lista)} respaldo(s) disponibles. Se crea uno "
                       "automáticamente antes de cada guardado; se conservan "
                       "todos los de hoy, uno por día (30 días) y uno por mes "
                       "(1 año)." if lista else
                       "Todavía no hay ningún respaldo automático para esta "
                       "máquina.")).pack(fill="x", padx=18, pady=(10, 6))

        if not lista:
            footer = tk.Frame(self, bg=PANEL, padx=18)
            footer.pack(fill="x", side="bottom", pady=14)
            button(footer, "Cerrar", self.destroy, kind="primary").pack(side="right")
            return

        wrap = tk.Frame(self, bg=PANEL, padx=18)
        wrap.pack(fill="both", expand=True)
        canvas, inner = build_scrollable_canvas(self, wrap)

        for b in lista:
            ok_hash = backups.verificar_integridad(b)
            card = tk.Frame(inner, bg=WHITE, highlightthickness=1,
                            highlightbackground=BORDER if ok_hash else RED_DARK)
            card.pack(fill="x", pady=(0, 8), padx=(0, 14))
            row = tk.Frame(card, bg=WHITE)
            row.pack(fill="x", padx=12, pady=8)
            texto = b.timestamp.strftime("%d/%m/%Y %H:%M:%S")
            kb = b.tamano_bytes / 1024
            tk.Label(row, text=f"{texto}   ·   {kb:.1f} KB", bg=WHITE, fg=TEXT,
                     font=FONT_BOLD, anchor="w").pack(side="left", fill="x", expand=True)
            if not ok_hash:
                tk.Label(row, text="⚠ hash no verificado", bg=WHITE, fg=RED_DARK,
                         font=FONT_SMALL).pack(side="left", padx=(0, 10))
            button(row, "Restaurar este backup", lambda bb=b: self._on_restaurar(bb),
                  kind="outline-danger", small=True).pack(side="right")

        footer = tk.Frame(self, bg=PANEL, padx=18)
        footer.pack(fill="x", side="bottom", pady=14)
        button(footer, "Cerrar", self.destroy, kind="secondary").pack(side="right")

    def _on_restaurar(self, backup) -> None:
        ok_hash = backups.verificar_integridad(backup)
        try:
            store_backup = DataStore.load(backup.ruta, self.profile)
        except (OSError, ValueError, UnicodeDecodeError, LookupError) as exc:
            error(self, "No se pudo leer el backup",
                 f"No se pudo leer el contenido de este backup para "
                 f"compararlo:\n\n{exc}")
            return

        resumen = backups.resumir_diferencias(self.store_actual, store_backup)
        partes = []
        if resumen["se_perderian"]:
            partes.append(f"{len(resumen['se_perderian'])} registro(s) que hoy "
                          "existen se PERDERÍAN")
        if resumen["se_recuperarian"]:
            partes.append(f"{len(resumen['se_recuperarian'])} registro(s) "
                          "borrados se RECUPERARÍAN")
        if resumen["cambiarian"]:
            partes.append(f"{len(resumen['cambiarian'])} registro(s) CAMBIARÍAN "
                          "de valor")
        detalle = "\n".join(f"  • {p}" for p in partes) if partes else \
            "  • No hay diferencias con el estado actual."

        advertencia_hash = ("\n\n⚠ El hash de este backup no se pudo verificar "
                            "(archivo sin sidecar .sha256, o alterado). Restaurarlo "
                            "de todos modos queda a tu criterio." if not ok_hash else "")

        if not confirm(self, "Confirmar restauración",
                      f"¿Restaurar el backup del {backup.timestamp:%d/%m/%Y %H:%M:%S}?\n\n"
                      f"Esto reemplaza TODO el archivo actual por ese punto en el "
                      f"tiempo:\n\n{detalle}{advertencia_hash}"):
            return

        try:
            backups.restaurar_backup(backup, self.path_actual)
        except OSError as exc:
            error(self, "No se pudo restaurar", f"No se pudo restaurar el backup:\n\n{exc}")
            return

        self.restaurado = True
        self.destroy()


# ============================================================================
#  Diálogo de historial de cambios (Nivel 2.2 / 2.4 del plan de mejoras)
# ============================================================================
ACCION_LABEL = {
    "alta": "Alta", "modificacion": "Modificación", "baja": "Baja",
    "importacion": "Importación", "restauracion": "Restauración",
    "limpieza": "Limpieza de metadatos",
}
ACCIONES_VALIDAS_ORDENADAS = ["alta", "modificacion", "baja", "importacion", "restauracion",
                              "limpieza"]
RANGOS_FECHA = ["Todos", "Últimos 7 días", "Últimos 30 días", "Últimos 90 días"]


class HistorialDialog(tk.Toplevel):
    """Visor de historial.jsonl: tabla filtrable por fecha, código y tipo de
    acción. No reconstruye el catálogo desde el log de eventos (2.4) — para
    volver a un punto en el tiempo se apoya en los backups automáticos
    (2.1), que ya son una copia exacta del archivo en ese momento y son más
    confiables que reconstruir a partir de un log de diffs por campo."""

    def __init__(self, parent, path_historial: str, data_dir: str,
                path_actual: str, profile: Profile, store: DataStore):
        super().__init__(parent)
        self.path_historial = path_historial
        self.data_dir = data_dir
        self.path_actual = path_actual
        self.profile = profile
        self.store = store
        self.restaurado = False

        self.title("Historial de cambios")
        self.configure(bg=PANEL)
        self.geometry("820x560")
        self.minsize(680, 400)
        self.transient(parent)

        self._todos = list(reversed(historial.leer_eventos(path_historial)))
        self._filtro_codigo = tk.StringVar()
        self._filtro_accion = tk.StringVar(value="Todas")
        self._filtro_fecha = tk.StringVar(value="Todos")

        self._build()
        self.after(50, _center_dialog, self, parent)
        self.wait_visibility()
        self.grab_set()
        self.bind("<Escape>", lambda e: self.destroy())
        self.wait_window(self)

    def _build(self) -> None:
        header = tk.Frame(self, bg=GREEN, height=56)
        header.pack(fill="x")
        header.pack_propagate(False)
        tk.Label(header, text="Historial de cambios", bg=GREEN, fg=WHITE,
                 font=("Segoe UI Semibold", 13)).pack(side="left", padx=18)

        filtros = tk.Frame(self, bg=PANEL, padx=18, pady=10)
        filtros.pack(fill="x")
        tk.Label(filtros, text="Código:", bg=PANEL, fg=TEXT, font=FONT_SMALL).pack(side="left")
        tb.Entry(filtros, textvariable=self._filtro_codigo, font=FONT_SMALL,
                width=16, bootstyle="success").pack(side="left", padx=(4, 14))
        tk.Label(filtros, text="Acción:", bg=PANEL, fg=TEXT, font=FONT_SMALL).pack(side="left")
        acciones = ["Todas"] + [ACCION_LABEL[a] for a in ACCIONES_VALIDAS_ORDENADAS]
        tb.Combobox(filtros, textvariable=self._filtro_accion, values=acciones,
                   state="readonly", font=FONT_SMALL, width=14).pack(side="left", padx=(4, 14))
        tk.Label(filtros, text="Fecha:", bg=PANEL, fg=TEXT, font=FONT_SMALL).pack(side="left")
        tb.Combobox(filtros, textvariable=self._filtro_fecha, values=RANGOS_FECHA,
                   state="readonly", font=FONT_SMALL, width=14).pack(side="left", padx=(4, 14))
        button(filtros, "Filtrar", self._refrescar, kind="primary", small=True).pack(side="left")

        self._info_label = tk.Label(self, bg=PANEL, fg=MUTED, font=FONT_SMALL, anchor="w")
        self._info_label.pack(fill="x", padx=18)

        table_wrap = tk.Frame(self, bg=BORDER, padx=1, pady=1)
        table_wrap.pack(fill="both", expand=True, padx=18, pady=(6, 8))
        cols = ("fecha", "accion", "clave", "usuario", "origen")
        self.tree = tb.Treeview(table_wrap, columns=cols, show="headings",
                                selectmode="browse", bootstyle="success")
        anchos = {"fecha": 150, "accion": 110, "clave": 140, "usuario": 110, "origen": 140}
        titulos = {"fecha": "Fecha", "accion": "Acción", "clave": "Código",
                  "usuario": "Usuario", "origen": "Origen"}
        for c in cols:
            self.tree.heading(c, text=titulos[c])
            self.tree.column(c, width=anchos[c], anchor="w")
        vsb = tb.Scrollbar(table_wrap, orient="vertical", command=self.tree.yview,
                          bootstyle="round")
        self.tree.configure(yscrollcommand=vsb.set)
        vsb.pack(side="right", fill="y")
        self.tree.pack(side="left", fill="both", expand=True)
        self.tree.bind("<Double-1>", lambda e: self._ver_detalle())

        footer = tk.Frame(self, bg=PANEL, padx=18)
        footer.pack(fill="x", pady=(0, 14))
        button(footer, "Cerrar", self.destroy, kind="secondary").pack(side="right")
        button(footer, "Ver detalle", self._ver_detalle, kind="outline").pack(
            side="right", padx=(0, 8))
        button(footer, "Exportar informe (CSV)…", self._exportar_informe,
              kind="outline",
              tooltip="Exportar los eventos filtrados (fecha, usuario, "
                      "valores anteriores/nuevos, versión) para adjuntar al "
                      "parte de cambio de receta.").pack(side="right", padx=(0, 8))
        button(footer, "🕐 Ver/restaurar backups…", self._abrir_backups,
              kind="outline-danger",
              tooltip="El historial registra QUÉ cambió; para volver a un "
                      "punto exacto en el tiempo se usa un backup automático "
                      "cercano a esa fecha.").pack(side="left")

        self._refrescar()

    def _exportar_informe(self) -> None:
        if not self._eventos_mostrados:
            warn(self, "Nada para exportar", "No hay eventos con los filtros actuales.")
            return
        dest = filedialog.asksaveasfilename(
            title="Exportar informe de cambios", defaultextension=".csv",
            initialfile="informe_cambios.csv", filetypes=[("CSV", "*.csv")])
        if not dest:
            return
        try:
            filas = informe.a_filas_csv(self._eventos_mostrados)
            with open(dest, "w", encoding="utf-8-sig", newline="") as f:
                csv.writer(f).writerows(filas)
        except OSError as exc:
            error(self, "Error al exportar", str(exc))
            return
        toast(self, f"Informe exportado a {os.path.basename(dest)}")

    def _eventos_filtrados(self) -> list[dict]:
        codigo = self._filtro_codigo.get().strip().lower()
        accion_label = self._filtro_accion.get()
        rango = self._filtro_fecha.get()

        limite = None
        if rango != "Todos":
            dias = {"Últimos 7 días": 7, "Últimos 30 días": 30,
                    "Últimos 90 días": 90}[rango]
            limite = datetime.now() - timedelta(days=dias)

        out = []
        for e in self._todos:
            if codigo and codigo not in str(e.get("clave", "")).lower():
                continue
            if accion_label != "Todas" and ACCION_LABEL.get(e.get("accion"), "") != accion_label:
                continue
            if limite is not None:
                try:
                    ts = datetime.fromisoformat(e["timestamp"])
                except (KeyError, ValueError):
                    continue
                if ts < limite:
                    continue
            out.append(e)
        return out

    def _refrescar(self) -> None:
        self.tree.delete(*self.tree.get_children())
        eventos = self._eventos_filtrados()
        for i, e in enumerate(eventos):
            ts = e.get("timestamp", "")
            try:
                ts_fmt = datetime.fromisoformat(ts).strftime("%d/%m/%Y %H:%M:%S")
            except (KeyError, ValueError, TypeError):
                ts_fmt = str(ts)
            self.tree.insert("", "end", iid=str(i), values=(
                ts_fmt, ACCION_LABEL.get(e.get("accion"), e.get("accion", "")),
                e.get("clave", ""), e.get("usuario", ""), e.get("origen", "")))
        self._eventos_mostrados = eventos
        self._info_label.config(text=f"{len(eventos)} de {len(self._todos)} evento(s)")

    def _ver_detalle(self) -> None:
        sel = self.tree.selection()
        if not sel:
            return
        e = self._eventos_mostrados[int(sel[0])]
        detalle = (
            f"Fecha: {e.get('timestamp', '')}\n"
            f"Usuario: {e.get('usuario', '')}\n"
            f"Acción: {ACCION_LABEL.get(e.get('accion'), e.get('accion', ''))}\n"
            f"Código: {e.get('clave', '')}\n"
            f"Origen: {e.get('origen', '')}\n\n"
            f"Valores anteriores:\n{json.dumps(e.get('anteriores'), ensure_ascii=False, indent=2)}\n\n"
            f"Valores nuevos:\n{json.dumps(e.get('nuevos'), ensure_ascii=False, indent=2)}")
        info(self, "Detalle del evento", detalle)

    def _abrir_backups(self) -> None:
        dlg = BackupsDialog(self, self.data_dir, self.path_actual, self.profile, self.store)
        if dlg.restaurado:
            self.restaurado = True
            self.destroy()


# ============================================================================
#  Vista de diferencias contra el original (Nivel 4.1)
# ============================================================================
TIPO_DIFF_LABEL = {"alta": "Alta", "baja": "Baja", "modificacion": "Modificación"}
TIPO_DIFF_COLOR = {"alta": GREEN_DARK, "baja": RED_DARK, "modificacion": AMBER}


class DiffsDialog(tk.Toplevel):
    """Comparación campo por campo entre `actual` y `original`, para que el
    operario pueda revisar exactamente qué cambió antes de subir el archivo
    al HMI. A diferencia del diff de importación (ImportDialog), esto es
    de solo lectura — no aplica ni descarta nada, solo informa."""

    def __init__(self, parent, store_actual: DataStore, store_original: DataStore):
        super().__init__(parent)
        self.profile = store_actual.profile
        self.diffs = diferencias.comparar_con_original(store_actual, store_original)
        self._tipos_activos = {"alta", "baja", "modificacion"}

        self.title("Ver cambios contra el original")
        self.configure(bg=PANEL)
        self.geometry("760x560")
        self.minsize(600, 400)
        self.transient(parent)

        self._build()
        self.after(50, _center_dialog, self, parent)
        self.wait_visibility()
        self.grab_set()
        self.bind("<Escape>", lambda e: self.destroy())
        self.wait_window(self)

    def _build(self) -> None:
        header = tk.Frame(self, bg=GREEN, height=56)
        header.pack(fill="x")
        header.pack_propagate(False)
        tk.Label(header, text="Cambios contra el original", bg=GREEN, fg=WHITE,
                 font=("Segoe UI Semibold", 13)).pack(side="left", padx=18)

        n_alta = sum(1 for d in self.diffs if d["tipo"] == "alta")
        n_baja = sum(1 for d in self.diffs if d["tipo"] == "baja")
        n_mod = sum(1 for d in self.diffs if d["tipo"] == "modificacion")
        tk.Label(self, bg=PANEL, fg=MUTED, font=FONT_SMALL, anchor="w",
                 text=(f"{n_alta} alta(s) · {n_baja} baja(s) · {n_mod} modificación(es)"
                       if self.diffs else
                       "No hay diferencias: el archivo actual es igual al original.")).pack(
            fill="x", padx=18, pady=(10, 4))

        filtros = tk.Frame(self, bg=PANEL, padx=18, pady=4)
        filtros.pack(fill="x")
        self._tipo_vars: dict[str, tk.BooleanVar] = {}
        for tipo in ("alta", "baja", "modificacion"):
            var = tk.BooleanVar(value=True)
            self._tipo_vars[tipo] = var
            tb.Checkbutton(filtros, text=TIPO_DIFF_LABEL[tipo], variable=var,
                          bootstyle="success", command=self._refrescar).pack(
                side="left", padx=(0, 14))

        table_wrap = tk.Frame(self, bg=BORDER, padx=1, pady=1)
        table_wrap.pack(fill="both", expand=True, padx=18, pady=(6, 8))
        cols = ("tipo", "codigo", "campos")
        self.tree = tb.Treeview(table_wrap, columns=cols, show="headings",
                                selectmode="browse", bootstyle="success")
        self.tree.heading("tipo", text="Tipo")
        self.tree.column("tipo", width=110, anchor="w")
        self.tree.heading("codigo", text="Código")
        self.tree.column("codigo", width=180, anchor="w")
        self.tree.heading("campos", text="Qué cambió")
        self.tree.column("campos", width=340, anchor="w")
        vsb = tb.Scrollbar(table_wrap, orient="vertical", command=self.tree.yview,
                          bootstyle="round")
        self.tree.configure(yscrollcommand=vsb.set)
        vsb.pack(side="right", fill="y")
        self.tree.pack(side="left", fill="both", expand=True)
        self.tree.bind("<Double-1>", lambda e: self._ver_detalle())

        footer = tk.Frame(self, bg=PANEL, padx=18)
        footer.pack(fill="x", pady=(0, 14))
        button(footer, "Cerrar", self.destroy, kind="secondary").pack(side="right")
        button(footer, "Ver detalle", self._ver_detalle, kind="outline").pack(
            side="right", padx=(0, 8))
        button(footer, "Exportar informe (CSV)…", self._exportar,
              kind="outline").pack(side="left")

        self._refrescar()

    def _diffs_filtrados(self) -> list[dict]:
        activos = {t for t, v in self._tipo_vars.items() if v.get()}
        return diferencias.filtrar_por_tipo(self.diffs, activos)

    def _refrescar(self) -> None:
        self.tree.delete(*self.tree.get_children())
        mostrados = self._diffs_filtrados()
        for i, d in enumerate(mostrados):
            if d["tipo"] == "modificacion":
                campos = [c.titulo_ui for c in self.profile.parametros_visibles()
                         if c.nombre_interno in d["campos_modificados"]]
                resumen = ", ".join(campos)
            else:
                resumen = ""
            self.tree.insert("", "end", iid=str(i),
                             tags=(d["tipo"],),
                             values=(TIPO_DIFF_LABEL[d["tipo"]], d["code"], resumen))
        for tipo, color in TIPO_DIFF_COLOR.items():
            self.tree.tag_configure(tipo, foreground=color)
        self._mostrados = mostrados

    def _ver_detalle(self) -> None:
        sel = self.tree.selection()
        if not sel:
            return
        d = self._mostrados[int(sel[0])]
        params = self.profile.parametros_visibles()
        if d["tipo"] == "modificacion":
            lineas = []
            for c in params:
                if c.nombre_interno in d["campos_modificados"]:
                    lineas.append(f"{c.titulo_ui}: {d['anteriores'][c.nombre_interno]} → "
                                  f"{d['nuevos'][c.nombre_interno]}")
            detalle = "\n".join(lineas)
        elif d["tipo"] == "alta":
            detalle = "\n".join(f"{c.titulo_ui}: {d['nuevos'].get(c.nombre_interno, '')}"
                               for c in params)
        else:
            detalle = "\n".join(f"{c.titulo_ui}: {d['anteriores'].get(c.nombre_interno, '')}"
                               for c in params)
        info(self, f"{TIPO_DIFF_LABEL[d['tipo']]} — {d['code']}", detalle)

    def _exportar(self) -> None:
        mostrados = self._diffs_filtrados()
        if not mostrados:
            warn(self, "Nada para exportar", "No hay diferencias con los filtros actuales.")
            return
        dest = filedialog.asksaveasfilename(
            title="Exportar informe de cambios", defaultextension=".csv",
            initialfile="cambios.csv", filetypes=[("CSV", "*.csv")])
        if not dest:
            return
        try:
            filas = diferencias.a_filas_csv(self.profile, mostrados)
            with open(dest, "w", encoding="utf-8-sig", newline="") as f:
                csv.writer(f).writerows(filas)
        except OSError as exc:
            error(self, "Error al exportar", str(exc))
            return
        toast(self, f"Informe exportado a {os.path.basename(dest)}")


# ============================================================================
#  Reporte de salud del catálogo (Nivel 4.5)
# ============================================================================
TIPO_HALLAZGO_LABEL = {"fuera_de_rango": "Fuera de rango",
                       "campo_vacio": "Campo vacío",
                       "duplicado": "Posible duplicado"}


class SaludDialog(tk.Toplevel):
    """Panel de salud: todos los hallazgos del catálogo en una sola lista,
    con acceso directo (doble clic) al registro correspondiente en la
    tabla principal."""

    def __init__(self, parent, store: DataStore, hallazgos: list):
        super().__init__(parent)
        self.app = parent
        self.store = store
        self.hallazgos = hallazgos
        self.slots_libres = salud.contar_slots_libres(store)

        self.title("Salud del catálogo")
        self.configure(bg=PANEL)
        self.geometry("720x520")
        self.minsize(560, 380)
        self.transient(parent)

        self._build()
        self.after(50, _center_dialog, self, parent)
        self.wait_visibility()
        self.grab_set()
        self.bind("<Escape>", lambda e: self.destroy())
        self.wait_window(self)

    def _build(self) -> None:
        header = tk.Frame(self, bg=GREEN, height=56)
        header.pack(fill="x")
        header.pack_propagate(False)
        tk.Label(header, text="Salud del catálogo", bg=GREEN, fg=WHITE,
                 font=("Segoe UI Semibold", 13)).pack(side="left", padx=18)

        resumen = tk.Frame(self, bg=PANEL, padx=18, pady=10)
        resumen.pack(fill="x")
        partes = [f"{len(self.hallazgos)} hallazgo(s)", f"{self.slots_libres} slot(s) libre(s)"]
        tk.Label(resumen, bg=PANEL, fg=MUTED, font=FONT_SMALL, anchor="w",
                 text=" · ".join(partes)).pack(fill="x")

        if not self.hallazgos:
            tk.Label(self, bg=PANEL, fg=GREEN_DARK, font=FONT,
                     text="✓ No se encontraron problemas en el catálogo.").pack(
                padx=18, pady=30)
            footer = tk.Frame(self, bg=PANEL, padx=18)
            footer.pack(fill="x", side="bottom", pady=14)
            button(footer, "Cerrar", self.destroy, kind="primary").pack(side="right")
            return

        table_wrap = tk.Frame(self, bg=BORDER, padx=1, pady=1)
        table_wrap.pack(fill="both", expand=True, padx=18, pady=(6, 8))
        cols = ("tipo", "codigo", "detalle")
        self.tree = tb.Treeview(table_wrap, columns=cols, show="headings",
                                selectmode="browse", bootstyle="success")
        self.tree.heading("tipo", text="Tipo")
        self.tree.column("tipo", width=140, anchor="w")
        self.tree.heading("codigo", text="Código")
        self.tree.column("codigo", width=160, anchor="w")
        self.tree.heading("detalle", text="Detalle")
        self.tree.column("detalle", width=280, anchor="w")
        vsb = tb.Scrollbar(table_wrap, orient="vertical", command=self.tree.yview,
                          bootstyle="round")
        self.tree.configure(yscrollcommand=vsb.set)
        vsb.pack(side="right", fill="y")
        self.tree.pack(side="left", fill="both", expand=True)
        self.tree.bind("<Double-1>", lambda e: self._ir_al_registro())

        for i, h in enumerate(self.hallazgos):
            self.tree.insert("", "end", iid=str(i), values=(
                TIPO_HALLAZGO_LABEL.get(h.tipo, h.tipo), h.code, h.mensaje))

        footer = tk.Frame(self, bg=PANEL, padx=18)
        footer.pack(fill="x", side="bottom", pady=14)
        button(footer, "Cerrar", self.destroy, kind="secondary").pack(side="right")
        button(footer, "Ir al registro", self._ir_al_registro, kind="primary").pack(
            side="right", padx=(0, 10))

    def _ir_al_registro(self) -> None:
        sel = self.tree.selection()
        if not sel:
            return
        h = self.hallazgos[int(sel[0])]
        self.destroy()
        self.app.ir_a_registro(h.code)


# ============================================================================
#  Filtros avanzados (Nivel 4.7)
# ============================================================================
class FiltrosDialog(tk.Toplevel):
    """Filtros de rango numérico sobre los parámetros del perfil, más una
    lista de combinaciones (búsqueda + rangos) guardadas por máquina para
    reaplicar con un clic."""

    def __init__(self, parent, app):
        super().__init__(parent)
        self.app = app
        self.profile = app.profile
        self.campos_numericos = [c for c in self.profile.parametros_visibles()
                                 if c.es_numerico]

        self.title("Filtros avanzados")
        self.configure(bg=PANEL)
        self.geometry("480x520")
        self.minsize(420, 380)
        self.transient(parent)

        self._entry_vars: dict[str, tuple[tk.StringVar, tk.StringVar]] = {}
        self._build()
        self.after(50, _center_dialog, self, parent)
        self.wait_visibility()
        self.grab_set()
        self.bind("<Escape>", lambda e: self.destroy())
        self.wait_window(self)

    def _build(self) -> None:
        header = tk.Frame(self, bg=GREEN, height=56)
        header.pack(fill="x")
        header.pack_propagate(False)
        tk.Label(header, text="Filtros avanzados", bg=GREEN, fg=WHITE,
                 font=("Segoe UI Semibold", 13)).pack(side="left", padx=18)

        tk.Label(self, bg=PANEL, fg=MUTED, font=FONT_SMALL, anchor="w",
                 text="Rango numérico (dejá vacío el que no quieras limitar):").pack(
            fill="x", padx=18, pady=(12, 6))

        form = tk.Frame(self, bg=PANEL)
        form.pack(fill="x", padx=18)
        rangos_actuales = self.app._filtros_rango
        for row, campo in enumerate(self.campos_numericos):
            tk.Label(form, text=campo.titulo_ui, bg=PANEL, fg=TEXT, font=FONT_BOLD,
                     anchor="w").grid(row=row, column=0, sticky="w", pady=4, padx=(0, 10))
            actual = rangos_actuales.get(campo.nombre_interno, (None, None))
            var_min = tk.StringVar(value="" if actual[0] is None else str(actual[0]))
            var_max = tk.StringVar(value="" if actual[1] is None else str(actual[1]))
            tk.Entry(form, textvariable=var_min, font=FONT_SMALL, width=8).grid(
                row=row, column=1, padx=(0, 4))
            tk.Label(form, text="a", bg=PANEL, fg=MUTED, font=FONT_SMALL).grid(
                row=row, column=2)
            tk.Entry(form, textvariable=var_max, font=FONT_SMALL, width=8).grid(
                row=row, column=3, padx=(4, 0))
            self._entry_vars[campo.nombre_interno] = (var_min, var_max)

        acciones = tk.Frame(self, bg=PANEL, padx=18, pady=8)
        acciones.pack(fill="x")
        button(acciones, "Limpiar filtros", self._on_limpiar, kind="outline",
              small=True).pack(side="left")
        button(acciones, "Guardar como…", self._on_guardar_preset, kind="outline",
              small=True,
              tooltip="Guardar la búsqueda + estos rangos como un filtro "
                      "frecuente para reaplicar después").pack(side="left", padx=(8, 0))

        tk.Label(self, bg=PANEL, fg=MUTED, font=FONT_SMALL, anchor="w",
                 text="Filtros guardados:").pack(fill="x", padx=18, pady=(6, 2))
        self._presets_frame = tk.Frame(self, bg=PANEL)
        self._presets_frame.pack(fill="both", expand=True, padx=18)
        self._refrescar_presets()

        footer = tk.Frame(self, bg=PANEL, padx=18)
        footer.pack(fill="x", pady=14)
        button(footer, "Cerrar", self.destroy, kind="secondary").pack(side="right")
        button(footer, "Aplicar", self._on_aplicar, kind="primary").pack(
            side="right", padx=(0, 10))

    def _refrescar_presets(self) -> None:
        for w in self._presets_frame.winfo_children():
            w.destroy()
        presets = filtros.cargar_guardados(self.app.data_dir)
        if not presets:
            tk.Label(self._presets_frame, bg=PANEL, fg=MUTED, font=FONT_SMALL,
                     text="(ninguno todavía)").pack(anchor="w")
            return
        for preset in presets:
            row = tk.Frame(self._presets_frame, bg=WHITE, highlightthickness=1,
                           highlightbackground=BORDER)
            row.pack(fill="x", pady=2)
            tk.Label(row, text=preset.get("nombre", ""), bg=WHITE, fg=TEXT,
                     font=FONT_SMALL, anchor="w").pack(side="left", padx=8, pady=4,
                                                       fill="x", expand=True)
            button(row, "Eliminar", lambda n=preset.get("nombre"): self._eliminar_preset(n),
                  kind="ghost", small=True).pack(side="right", padx=(0, 4))
            button(row, "Aplicar", lambda p=preset: self._aplicar_preset(p),
                  kind="outline", small=True).pack(side="right", padx=4)

    def _leer_rangos(self) -> dict:
        rangos = {}
        for nombre, (var_min, var_max) in self._entry_vars.items():
            texto_min, texto_max = var_min.get().strip(), var_max.get().strip()
            if not texto_min and not texto_max:
                continue
            try:
                minimo = float(texto_min) if texto_min else None
                maximo = float(texto_max) if texto_max else None
            except ValueError:
                continue  # entrada no numérica: se ignora ese campo, no bloquea el resto
            rangos[nombre] = (minimo, maximo)
        return rangos

    def _on_aplicar(self) -> None:
        self.app._filtros_rango = self._leer_rangos()
        self.app.refresh_table()
        self.destroy()

    def _on_limpiar(self) -> None:
        for var_min, var_max in self._entry_vars.values():
            var_min.set("")
            var_max.set("")
        self.app._filtros_rango = {}
        self.app.refresh_table()

    def _on_guardar_preset(self) -> None:
        nombre = Querybox.get_string(
            prompt="Nombre para este filtro (búsqueda + rangos actuales):",
            title="Guardar filtro", parent=self)
        if not nombre or not nombre.strip():
            return
        filtros.agregar_o_reemplazar(self.app.data_dir, nombre.strip(),
                                     self.app.search_var.get(), self._leer_rangos())
        self._refrescar_presets()

    def _aplicar_preset(self, preset: dict) -> None:
        self.app.search_var.set(preset.get("busqueda", ""))
        rangos_preset = preset.get("rangos", {})
        for nombre, (var_min, var_max) in self._entry_vars.items():
            rango = rangos_preset.get(nombre)
            if rango:
                var_min.set("" if rango[0] is None else str(rango[0]))
                var_max.set("" if rango[1] is None else str(rango[1]))
            else:
                var_min.set("")
                var_max.set("")
        self._on_aplicar()

    def _eliminar_preset(self, nombre: str) -> None:
        filtros.eliminar(self.app.data_dir, nombre)
        self._refrescar_presets()


# ============================================================================
#  Edición masiva (Nivel 4.8)
# ============================================================================
class BulkEditDialog(tk.Toplevel):
    """Aplica un mismo valor a un campo de TODOS los registros
    seleccionados de una vez, con la misma validación que la edición
    individual. Queda registrado como un solo comando deshacible (un
    Ctrl+Z revierte todos los registros tocados juntos, no uno por uno)."""

    def __init__(self, parent, app, indices: list[int]):
        super().__init__(parent)
        self.app = app
        self.profile = app.profile
        self.indices = indices
        self.campos = [c for c in self.profile.parametros_visibles()]
        self.aplicado = False

        self.title("Editar en masa")
        self.configure(bg=PANEL)
        self.geometry("420x260")
        self.minsize(380, 220)
        self.transient(parent)

        self._build()
        self.after(50, _center_dialog, self, parent)
        self.wait_visibility()
        self.grab_set()
        self.bind("<Escape>", lambda e: self.destroy())
        self.wait_window(self)

    def _build(self) -> None:
        header = tk.Frame(self, bg=GREEN, height=52)
        header.pack(fill="x")
        header.pack_propagate(False)
        tk.Label(header, text="Editar en masa", bg=GREEN, fg=WHITE,
                 font=("Segoe UI Semibold", 13)).pack(side="left", padx=18)

        tk.Label(self, bg=PANEL, fg=MUTED, font=FONT_SMALL, anchor="w",
                 justify="left",
                 text=f"Se va a aplicar el mismo valor a los {len(self.indices)} "
                     "registro(s) seleccionados.").pack(fill="x", padx=18, pady=(14, 10))

        form = tk.Frame(self, bg=PANEL)
        form.pack(fill="x", padx=18)
        form.columnconfigure(1, weight=1)
        tk.Label(form, text="Campo", bg=PANEL, fg=TEXT, font=FONT_BOLD,
                 anchor="w").grid(row=0, column=0, sticky="w", pady=8, padx=(0, 12))
        self._campo_var = tk.StringVar(value=self.campos[0].titulo_ui if self.campos else "")
        titulos = [c.titulo_ui for c in self.campos]
        tb.Combobox(form, textvariable=self._campo_var, values=titulos,
                   state="readonly", font=FONT, width=24,
                   bootstyle="success").grid(row=0, column=1, sticky="we", pady=8)

        tk.Label(form, text="Valor nuevo", bg=PANEL, fg=TEXT, font=FONT_BOLD,
                 anchor="w").grid(row=1, column=0, sticky="w", pady=8, padx=(0, 12))
        self._valor_var = tk.StringVar()
        tb.Entry(form, textvariable=self._valor_var, font=FONT,
                bootstyle="success").grid(row=1, column=1, sticky="we", pady=8)

        footer = tk.Frame(self, bg=PANEL, padx=18)
        footer.pack(fill="x", side="bottom", pady=14)
        button(footer, "Cancelar", self.destroy, kind="secondary").pack(side="right")
        button(footer, f"Aplicar a {len(self.indices)}", self._on_aplicar,
              kind="primary").pack(side="right", padx=(0, 10))

    def _campo_elegido(self) -> Campo:
        titulo = self._campo_var.get()
        return next(c for c in self.campos if c.titulo_ui == titulo)

    def _on_aplicar(self) -> None:
        campo = self._campo_elegido()
        valor, error = validacion.parsear_valor_campo(campo, self._valor_var.get())
        if error:
            warn(self, "Revisá el valor", error)
            return
        if not confirm(self, "Confirmar edición masiva",
                       f"¿Poner «{campo.titulo_ui}» = {valor} en "
                       f"{len(self.indices)} registro(s)? Esta acción se puede "
                       "deshacer con Ctrl+Z."):
            return

        cambios = []
        for idx in self.indices:
            anterior = dict(self.app.store.records[idx])
            self.app.store.update(idx, {campo.nombre_interno: valor})
            nuevo = dict(self.app.store.records[idx])
            cambios.append(CambioRegistro("modificacion", self.app.store.key_of(nuevo),
                                          anteriores=anterior, nuevos=nuevo))

        guardado_ok = self.app._autosave()
        self.app.refresh_table()
        if guardado_ok:
            self.app._registrar_cambios(
                f"edición masiva de «{campo.titulo_ui}» en {len(cambios)} registro(s)",
                cambios)
            toast(self.app, f"{len(cambios)} registro(s) actualizados.")
        self.aplicado = True
        self.destroy()


# ============================================================================
#  Panel multi-máquina (Nivel 4.9)
# ============================================================================
class PanelMultiMaquinaDialog(tk.Toplevel):
    """Vista consolidada de todas las máquinas configuradas: una fila por
    máquina, de solo lectura, con doble clic para saltar directo a
    administrarla (reutiliza App._activate_profile, con el mismo control de
    instancia única que el selector normal)."""

    def __init__(self, parent, app):
        super().__init__(parent)
        self.app = app
        self.title("Panel multi-máquina")
        self.configure(bg=PANEL)
        self.geometry("760x480")
        self.minsize(600, 360)
        self.transient(parent)

        self._resumenes = panel_multi_maquina.resumen_de_todas(app._all_profiles)
        self._build()
        self.after(50, _center_dialog, self, parent)
        self.wait_visibility()
        self.grab_set()
        self.bind("<Escape>", lambda e: self.destroy())
        self.wait_window(self)

    def _build(self) -> None:
        header = tk.Frame(self, bg=GREEN, height=56)
        header.pack(fill="x")
        header.pack_propagate(False)
        tk.Label(header, text="Panel multi-máquina", bg=GREEN, fg=WHITE,
                 font=("Segoe UI Semibold", 13)).pack(side="left", padx=18)

        tk.Label(self, bg=PANEL, fg=MUTED, font=FONT_SMALL, anchor="w",
                 text=f"{len(self._resumenes)} máquina(s). Doble clic en una fila "
                     "para administrarla.").pack(fill="x", padx=18, pady=(10, 6))

        table_wrap = tk.Frame(self, bg=BORDER, padx=1, pady=1)
        table_wrap.pack(fill="both", expand=True, padx=18, pady=(0, 8))
        cols = ("nombre", "registros", "modificado", "duplicados", "salud")
        self.tree = tb.Treeview(table_wrap, columns=cols, show="headings",
                                selectmode="browse", bootstyle="success")
        titulos = {"nombre": "Máquina", "registros": "Registros",
                  "modificado": "Última modificación", "duplicados": "Duplicados",
                  "salud": "Alertas de salud"}
        anchos = {"nombre": 200, "registros": 90, "modificado": 170,
                 "duplicados": 100, "salud": 110}
        for c in cols:
            self.tree.heading(c, text=titulos[c])
            self.tree.column(c, width=anchos[c],
                             anchor="w" if c in ("nombre", "modificado") else "center")
        vsb = tb.Scrollbar(table_wrap, orient="vertical", command=self.tree.yview,
                          bootstyle="round")
        self.tree.configure(yscrollcommand=vsb.set)
        vsb.pack(side="right", fill="y")
        self.tree.pack(side="left", fill="both", expand=True)
        self.tree.tag_configure("error", foreground=RED_DARK)
        self.tree.tag_configure("alerta", foreground=AMBER)
        self.tree.bind("<Double-1>", lambda e: self._ir_a_maquina())

        for i, r in enumerate(self._resumenes):
            if r.error:
                self.tree.insert("", "end", iid=str(i), tags=("error",),
                                 values=(r.nombre, "—", "—", "—", f"⚠ {r.error}"))
                continue
            ts_fmt = r.ultima_modificacion
            try:
                ts_fmt = datetime.fromisoformat(r.ultima_modificacion).strftime(
                    "%d/%m/%Y %H:%M")
            except (ValueError, TypeError):
                pass
            tags = ("alerta",) if r.alertas_salud else ()
            self.tree.insert("", "end", iid=str(i), tags=tags, values=(
                r.nombre, r.cantidad_registros, ts_fmt,
                r.duplicados_pendientes, r.alertas_salud))

        footer = tk.Frame(self, bg=PANEL, padx=18)
        footer.pack(fill="x", pady=(0, 14))
        button(footer, "Cerrar", self.destroy, kind="secondary").pack(side="right")
        button(footer, "Administrar esta máquina", self._ir_a_maquina,
              kind="primary").pack(side="right", padx=(0, 10))

    def _ir_a_maquina(self) -> None:
        sel = self.tree.selection()
        if not sel:
            return
        resumen = self._resumenes[int(sel[0])]
        profile = next((p for p in self.app._all_profiles if p.id == resumen.id), None)
        if profile is None:
            return
        self.destroy()
        if profile.id != self.app.profile.id:
            self.app._activate_profile(profile)


# ============================================================================
#  Ventana principal
# ============================================================================
class App(tb.Window):
    def __init__(self, profiles: list[Profile]):
        super().__init__(title=APP_TITLE, themename="litera")
        apply_theme(self)
        self.geometry("1150x680")
        self.minsize(1100, 560)
        self.configure(bg=BG)

        self._all_profiles = profiles
        self.search_var = tk.StringVar()
        self.show_placeholders = tk.BooleanVar(value=False)
        self._sort_col: str | None = None
        self._sort_reverse = False

        if len(profiles) == 1:
            chosen = profiles[0]
        else:
            # No ocultar la ventana principal antes de abrir el selector: en
            # Windows, un Toplevel transient() de una ventana withdrawn()
            # queda con winfo_viewable()=0 y nunca llega a mostrarse, aunque
            # su estado reporte "normal" (la app parece colgada al iniciar).
            self.update_idletasks()
            sel = MachineSelector(self, profiles)
            chosen = sel.result or profiles[0]
            self._reload_all_profiles()

        self.protocol("WM_DELETE_WINDOW", self._on_close)
        self._activate_profile(chosen)
        if not hasattr(self, "store"):
            # _activate_profile decidió que no hay ninguna máquina utilizable
            # (archivo corrupto sin recuperación posible) y ya se destruyó a
            # sí misma: no seguir configurando una ventana que ya no existe.
            return
        self.search_var.trace_add("write", lambda *_: self.refresh_table())
        self.bind("<Control-n>", lambda e: self.on_new())
        self.bind("<Control-f>", lambda e: self.search_entry.focus_set())
        self.bind("<Control-z>", lambda e: self.on_deshacer())
        self.bind("<Control-y>", lambda e: self.on_rehacer())

    def _on_close(self) -> None:
        """Suelta el lock de instancia única (4.4) antes de cerrar — si no,
        la próxima apertura de esta máquina se vería bloqueada por un
        proceso que ya terminó normalmente (no un crash: liberar() acá es
        el camino feliz; _proceso_vivo() en instancia.py cubre el caso del
        proceso que muere sin llegar a liberar, p. ej. por un crash)."""
        lock_dir = getattr(self, "_lock_data_dir", None)
        if lock_dir:
            instancia.liberar(lock_dir)
        self.destroy()

    def _reload_all_profiles(self) -> None:
        """Releer profiles/*.json desde disco y usarlo como lista de
        máquinas: el selector puede crear, editar o eliminar máquinas por
        dentro (incluso en cascada, con sus propios sub-diálogos), y el
        disco es la única fuente de verdad — más simple y confiable que ir
        parchando self._all_profiles a mano por cada acción posible."""
        perfiles, _errores = _cargar_perfiles()
        if perfiles:
            self._all_profiles = perfiles

    # -- activación de perfil (datos + migración + UI) -------------------------
    def _activate_profile(self, profile: Profile) -> None:
        """Activa `profile` como la máquina en uso. Deliberadamente NO toca
        self.profile/self.store/las rutas hasta el final, cuando ya se sabe
        que la carga tuvo éxito: si algo falla en el medio (archivo
        corrupto, seed que no se pudo escribir), la app tiene que quedar
        exactamente como estaba antes de intentar el cambio — nunca con
        self.profile apuntando a una máquina distinta de self.store."""
        data_dir = paths.data_dir_for(profile.id)
        ext = profile.extension
        path_original = os.path.join(data_dir, f"original.{ext}")
        path_actual = os.path.join(data_dir, f"actual.{ext}")
        path_meta = os.path.join(data_dir, "meta.json")
        es_primera_activacion = not hasattr(self, "store")

        lock_previo = getattr(self, "_lock_data_dir", None)
        lock_nuevo_tomado_aca = False
        if lock_previo != data_dir:
            try:
                instancia.adquirir(data_dir)
                lock_nuevo_tomado_aca = True
            except instancia.InstanciaBloqueadaError as exc:
                info_bloqueo = exc.info
                error(self, "Esta máquina ya está abierta",
                     f"«{profile.nombre}» ya está abierta en otra ventana de "
                     f"esta misma PC (proceso {info_bloqueo.get('pid')}, "
                     f"desde {info_bloqueo.get('timestamp', 'hace un momento')}).\n\n"
                     "Cerrá esa ventana antes de abrir la misma máquina acá — "
                     "abrirla dos veces haría que la segunda pisara los "
                     "cambios de la primera sin avisar.")
                if es_primera_activacion:
                    self.destroy()
                return

        if not os.path.exists(path_actual):
            try:
                self._seed_or_migrate(profile, path_original, path_actual, path_meta)
            except OSError as exc:
                error(self, "No se pudo preparar la máquina",
                     f"No se pudieron crear los archivos iniciales de "
                     f"«{profile.nombre}»:\n\n{exc}")
                if lock_nuevo_tomado_aca:
                    instancia.liberar(data_dir)
                if es_primera_activacion:
                    self.destroy()
                return

        store = self._cargar_datastore_resiliente(profile, path_original, path_actual)
        if store is None:
            # El usuario canceló la recuperación: si es la primera máquina
            # que se intenta abrir al arrancar, no hay ningún estado previo
            # al que volver — cerramos en vez de dejar la app a medio armar.
            # Si es un cambio de máquina, la máquina anterior sigue activa
            # tal cual estaba (self.profile/self.store no se tocaron).
            if lock_nuevo_tomado_aca:
                instancia.liberar(data_dir)
            if es_primera_activacion:
                self.destroy()
            return

        if lock_previo and lock_previo != data_dir:
            instancia.liberar(lock_previo)  # se cambió de máquina: soltar la anterior
        self._lock_data_dir = data_dir

        self.profile = profile
        self.data_dir = data_dir
        self.path_original = path_original
        self.path_actual = path_actual
        self.path_meta = path_meta
        self.path_historial = os.path.join(data_dir, "historial.jsonl")
        self.store = store
        self._hash_conocido = deteccion_externa.hash_archivo(path_actual)
        log_config.get_logger().info(
            "Máquina activada: %s (%s), %d registro(s)",
            profile.id, profile.nombre, len(store.records))
        self.sidecar = Sidecar.load(self.path_meta)
        # La pila de deshacer/rehacer es por máquina activa: no tiene
        # sentido "deshacer" en la máquina B algo que se hizo en la A.
        self._pila_deshacer: list[ComandoDeshacer] = []
        self._pila_rehacer: list[ComandoDeshacer] = []
        self._avisar_si_sidecar_corrupto()
        self._avisar_si_columnas_fantasma()
        self._purgar_backups_y_historial()
        self._sort_col = None
        self._filtros_rango = {}  # los filtros de rango son por máquina, como el orden
        self._delete_mode = False
        self._build_ui()
        self.refresh_table()
        self._actualizar_botones_deshacer()

    def _purgar_backups_y_historial(self) -> None:
        """Aplica la política de retención de backups (2.1) y del historial
        (2.2) una vez por activación de máquina. Best-effort: si falla (p.
        ej. permisos), no debe impedir abrir la máquina — solo se pierde la
        limpieza automática, no ningún dato."""
        try:
            backups.purgar_backups(self.data_dir)
        except OSError:
            pass
        try:
            historial.rotar_si_hace_falta(self.path_historial)
            historial.purgar_eventos_viejos(self.path_historial)
        except OSError:
            pass

    def _registrar_evento(self, accion: str, clave: str, anteriores: dict | None = None,
                          nuevos: dict | None = None, origen: str = "manual") -> None:
        """Registra un evento suelto en el historial (sin pasar por la pila
        de deshacer). Usar _registrar_cambios() en vez de esto para
        cualquier mutación que el usuario deba poder deshacer con Ctrl+Z —
        este método queda para casos que no son reversibles como comando
        único (restauraciones completas, p. ej.). Best-effort y NUNCA
        bloquea al usuario: si falla (permisos, disco lleno), el cambio
        real ya se guardó en actual.<ext> — perder una línea de
        trazabilidad es mucho menos grave que no poder guardar el dato."""
        try:
            historial.registrar(self.path_historial, accion, clave,
                               anteriores=anteriores, nuevos=nuevos, origen=origen,
                               version=version.APP_VERSION)
        except OSError:
            pass

    # -- Deshacer / Rehacer (Nivel 2.3) -----------------------------------------
    def _registrar_cambios(self, descripcion: str, cambios: list[CambioRegistro],
                           origen: str = "manual") -> None:
        """Registra en el historial CADA cambio individual, y apila el
        comando completo (todos los cambios juntos) como una sola unidad
        deshacible con Ctrl+Z. Se llama DESPUÉS de que el autoguardado ya
        confirmó éxito — no tiene sentido poder "deshacer" algo que ni
        siquiera se llegó a persistir."""
        for c in cambios:
            self._registrar_evento(c.accion, c.clave, anteriores=c.anteriores,
                                   nuevos=c.nuevos, origen=origen)
        self._pila_deshacer.append(ComandoDeshacer(descripcion, cambios))
        if len(self._pila_deshacer) > LIMITE_DESHACER:
            self._pila_deshacer.pop(0)
        self._pila_rehacer.clear()
        self._actualizar_botones_deshacer()

    def _aplicar_inverso(self, cambios: list[CambioRegistro]) -> None:
        """Revierte una lista de cambios, en orden INVERSO al que se
        aplicaron (importante si varios cambios de la lista tocan registros
        relacionados)."""
        clave_campo = self.profile.campo_clave().nombre_interno
        for c in reversed(cambios):
            if c.accion == "alta":
                idx = self.store.find_key(c.clave)
                if idx != -1:
                    self.store.delete(idx)
            elif c.accion == "baja":
                self.store.add(dict(c.anteriores))
            elif c.accion == "modificacion":
                idx = self.store.find_key(c.nuevos[clave_campo])
                if idx != -1:
                    self.store.update(idx, dict(c.anteriores))

    def _aplicar_directo(self, cambios: list[CambioRegistro]) -> None:
        """Vuelve a aplicar una lista de cambios en el orden ORIGINAL (usado
        al rehacer, y para deshacer el propio deshacer si el guardado
        posterior falla)."""
        clave_campo = self.profile.campo_clave().nombre_interno
        for c in cambios:
            if c.accion == "alta":
                self.store.add(dict(c.nuevos))
            elif c.accion == "baja":
                idx = self.store.find_key(c.clave)
                if idx != -1:
                    self.store.delete(idx)
            elif c.accion == "modificacion":
                idx = self.store.find_key(c.anteriores[clave_campo])
                if idx != -1:
                    self.store.update(idx, dict(c.nuevos))

    def on_deshacer(self) -> None:
        if not self._pila_deshacer:
            self._set_status("Nada para deshacer")
            return
        comando = self._pila_deshacer.pop()
        self._aplicar_inverso(comando.cambios)
        guardado_ok = self._autosave()
        self.refresh_table()
        if not guardado_ok:
            # El guardado falló: dejamos el store como estaba (reaplicando
            # el cambio original) y la pila intacta, como si Ctrl+Z nunca
            # se hubiera apretado.
            self._aplicar_directo(comando.cambios)
            self._pila_deshacer.append(comando)
            self.refresh_table()
            self._actualizar_botones_deshacer()
            return
        for c in reversed(comando.cambios):
            self._registrar_evento(c.accion, c.clave, anteriores=c.nuevos,
                                   nuevos=c.anteriores, origen="deshacer")
        self._pila_rehacer.append(comando)
        self._actualizar_botones_deshacer()
        toast(self, f"Deshecho: {comando.descripcion}", kind="warning")

    def on_rehacer(self) -> None:
        if not self._pila_rehacer:
            self._set_status("Nada para rehacer")
            return
        comando = self._pila_rehacer.pop()
        self._aplicar_directo(comando.cambios)
        guardado_ok = self._autosave()
        self.refresh_table()
        if not guardado_ok:
            self._aplicar_inverso(comando.cambios)
            self._pila_rehacer.append(comando)
            self.refresh_table()
            self._actualizar_botones_deshacer()
            return
        for c in comando.cambios:
            self._registrar_evento(c.accion, c.clave, anteriores=c.anteriores,
                                   nuevos=c.nuevos, origen="rehacer")
        self._pila_deshacer.append(comando)
        self._actualizar_botones_deshacer()
        toast(self, f"Rehecho: {comando.descripcion}", kind="warning")

    def _actualizar_botones_deshacer(self) -> None:
        if not hasattr(self, "undo_btn"):
            return
        self.undo_btn.config(state="normal" if self._pila_deshacer else "disabled")
        self.redo_btn.config(state="normal" if self._pila_rehacer else "disabled")

    def _avisar_si_columnas_fantasma(self) -> None:
        """DataStore.load() detecta si el archivo tiene datos más allá del
        último registro reconocido (ver _detectar_columnas_fantasma en
        datastore.py) — algo que antes se descartaba en silencio. Se avisa
        una sola vez por activación, con el detalle completo."""
        if not self.store.advertencias:
            return
        detalle = "\n\n".join(self.store.advertencias)
        warn(self, "Posibles datos no cargados",
            "Se detectaron celdas con datos que NO se cargaron porque están "
            "más allá del último registro reconocido en el archivo:\n\n"
            f"{detalle}\n\n"
            "Puede tratarse de datos residuales sin importancia, o de un "
            "registro real que quedó fuera. Si corresponde, revisá el "
            "archivo con un editor de texto/Excel antes de seguir editando "
            "desde esta app.")

    def _cargar_datastore_resiliente(self, profile: Profile, path_original: str,
                                     path_actual: str) -> "DataStore | None":
        """Carga actual.<ext> con manejo de errores: un archivo corrupto, con
        una codificación inesperada, o que ya no matchea el perfil (p. ej. el
        formato se editó y el archivo vivo quedó desincronizado) no debe
        crashear la app con un traceback sin ninguna salida. Devuelve None
        si el usuario decide no continuar (cancelar)."""
        while True:
            try:
                return DataStore.load(path_actual, profile)
            except (OSError, ValueError, UnicodeDecodeError, LookupError) as exc:
                opcion = preguntar_opciones(
                    self, "No se pudo abrir la máquina",
                    f"No se pudo leer el archivo actual de «{profile.nombre}»:\n\n"
                    f"{exc}\n\n¿Qué querés hacer?",
                    ["Reintentar:secondary", "Restaurar el original:warning",
                     "Cancelar:danger"])
                if opcion == "Reintentar":
                    continue
                if opcion == "Restaurar el original":
                    try:
                        copiar_atomico(path_original, path_actual)
                    except OSError as exc2:
                        error(self, "No se pudo restaurar",
                             f"No se pudo copiar el archivo original:\n\n{exc2}")
                    continue
                return None

    def _avisar_si_sidecar_corrupto(self) -> None:
        """El sidecar de metadatos (marcas de 'no es duplicado', etc.) puede
        llegar corrupto o ilegible. Antes esto se descartaba en silencio y
        arrancaba vacío sin que nadie se enterara; ahora se avisa siempre,
        aunque el archivo dañado ya se haya aislado a un costado."""
        if not self.sidecar.recuperado_de_corrupcion:
            return
        detalle = (f"\n\nEl archivo dañado se guardó como respaldo en:\n"
                   f"{self.sidecar.ruta_respaldo_corrupto}"
                   if self.sidecar.ruta_respaldo_corrupto else
                   "\n\n(no se pudo aislar el archivo dañado; sigue en su "
                   "ubicación original y se va a sobrescribir al primer "
                   "guardado)")
        warn(self, "Metadatos de la máquina dañados",
            "El archivo de metadatos de esta máquina (marcas de \"no es "
            "duplicado\", etc.) estaba corrupto o no se pudo leer:\n\n"
            f"{self.sidecar.motivo_corrupcion}\n\n"
            "Se continuó SIN esas marcas — puede que reaparezcan como "
            f"posibles duplicados registros ya revisados antes.{detalle}")

    def _seed_or_migrate(self, profile: Profile, path_original: str,
                         path_actual: str, path_meta: str) -> None:
        arranque.seed_or_migrate(profile, path_original, path_actual, path_meta)

    def _resolver_modificacion_externa(self) -> str:
        """Detecta si `actual.<ext>` cambió por fuera de la app desde la
        última vez que se leyó o escribió (Nivel 4.3): alguien lo copió a
        mano, un script, o la propia máquina. Devuelve "sobrescribir" (no
        hay conflicto, o el usuario decide pisarlo igual), "recargar" (el
        usuario quiere descartar los cambios en memoria y tomar lo que hay
        en disco), o "cancelar" (no guardar nada por ahora)."""
        if not deteccion_externa.fue_modificado_externamente(
                self.path_actual, self._hash_conocido):
            return "sobrescribir"
        while True:
            opcion = preguntar_opciones(
                self, "El archivo cambió por fuera de la app",
                f"«{os.path.basename(self.path_actual)}» fue modificado "
                "desde la última vez que esta app lo leyó — puede que otro "
                "programa, un script, o alguien más lo haya tocado.\n\n"
                "¿Qué querés hacer con tus cambios en memoria?",
                ["Ver diferencias:secondary", "Recargar desde disco:warning",
                 "Sobrescribir con lo mío:danger", "Cancelar:secondary"])
            if opcion == "Ver diferencias":
                try:
                    store_disco = DataStore.load(self.path_actual, self.profile)
                except (OSError, ValueError, UnicodeDecodeError, LookupError) as exc:
                    error(self, "No se pudo leer el archivo en disco", str(exc))
                    continue
                DiffsDialog(self, self.store, store_disco)
                continue
            if opcion == "Recargar desde disco":
                return "recargar"
            if opcion == "Sobrescribir con lo mío":
                return "sobrescribir"
            return "cancelar"

    def _recargar_desde_disco(self) -> None:
        try:
            nuevo_store = DataStore.load(self.path_actual, self.profile)
        except (OSError, ValueError, UnicodeDecodeError, LookupError) as exc:
            error(self, "No se pudo recargar",
                 f"No se pudo leer el archivo desde disco:\n\n{exc}\n\n"
                 "Tus cambios en memoria NO se modificaron.")
            return
        self.store = nuevo_store
        self._hash_conocido = deteccion_externa.hash_archivo(self.path_actual)
        self._pila_deshacer.clear()
        self._pila_rehacer.clear()
        self._actualizar_botones_deshacer()
        self.refresh_table()
        log_config.get_logger().info("Recargado desde disco tras detectar modificación externa: %s",
                                     self.path_actual)
        self._set_status("Se recargó desde disco — tus cambios en memoria se descartaron",
                         fg=AMBER)

    def _autosave(self) -> bool:
        """Guarda los cambios en el archivo actual, con manejo de errores y
        verificación post-escritura. Devuelve True solo si se guardó Y se
        verificó correctamente. El llamador NO debe reportar la acción
        (toast de éxito) si esto devuelve False — ya se avisó al usuario acá
        que los cambios NO quedaron persistidos, y no hay que confundirlo
        con un mensaje de éxito superpuesto."""
        accion = self._resolver_modificacion_externa()
        if accion == "cancelar":
            self._set_status("Guardado cancelado — el archivo había cambiado por fuera",
                             fg=AMBER)
            return False
        if accion == "recargar":
            self._recargar_desde_disco()
            return False
        try:
            # Respaldo del estado VIGENTE antes de sobreescribirlo (best-effort:
            # si falla, no debe impedir guardar el cambio real del usuario —
            # perder un backup puntual es mucho menos grave que no poder
            # guardar en absoluto).
            backups.crear_backup(self.data_dir, self.path_actual, self.profile.extension)
        except OSError:
            pass
        try:
            self.store.save(self.path_actual)
        except OSError as exc:
            log_config.get_logger().error(
                "Guardado falló para %s: %s", self.path_actual, exc)
            self._reportar_fallo_de_guardado(str(exc))
            return False

        if not self._verificar_guardado():
            log_config.get_logger().error(
                "Guardado no verificó tras escribir %s", self.path_actual)
            self._reportar_fallo_de_guardado(
                "el archivo se escribió pero su contenido no coincide con lo "
                "esperado al releerlo. Puede deberse a otro programa "
                "interfiriendo (por ejemplo un antivirus) o a un problema "
                "del disco.")
            return False

        log_config.get_logger().info("Guardado OK: %s", self.path_actual)
        self._hash_conocido = deteccion_externa.hash_archivo(self.path_actual)
        self._set_status("Cambios guardados")
        return True

    def _verificar_guardado(self) -> bool:
        encoding = "utf-8-sig" if self.profile.bom else self.profile.encoding
        return verificar_contenido(self.path_actual, self.store.to_text(), encoding)

    def _reportar_fallo_de_guardado(self, motivo: str) -> None:
        self._set_status("⚠ Cambios SIN guardar — no subas este archivo a la máquina",
                         fg=RED_DARK)
        error(self, "No se pudieron guardar los cambios",
              "NO se pudieron guardar los cambios en el archivo de la "
              f"máquina:\n\n{motivo}\n\n"
              "El archivo en disco puede no reflejar tu última edición. "
              "NO subas este archivo al HMI hasta resolver el problema "
              "(por ejemplo, liberar espacio en disco, cerrar programas "
              "que puedan estar bloqueando el archivo, o revisar la "
              "conexión si la carpeta está en red) y volver a intentar "
              "la acción.")

    def _guardar_sidecar(self) -> bool:
        """Guarda los metadatos propios de la app (flags de 'no duplicado',
        etc.). A diferencia de _autosave(), un fallo acá no compromete el
        archivo que va al HMI — pero igual hay que avisar, porque si no se
        guarda, esas marcas se pierden en silencio la próxima vez que se
        cargue la máquina.

        De paso, limpia metadatos huérfanos (Nivel 2.5): claves marcadas
        que ya no existen en el catálogo vigente (p. ej. de un registro
        borrado hace tiempo), que si no se limpian quedan pegadas para
        siempre en meta.json."""
        try:
            claves_validas = {self.store.key_of(r) for r in self.store.records}
            limpiadas = self.sidecar.save(claves_validas=claves_validas)
            if limpiadas:
                self._registrar_evento(
                    "limpieza", "*", anteriores={"metadatos_huerfanos": limpiadas},
                    origen="limpieza_automatica")
            return True
        except OSError as exc:
            self._set_status("⚠ No se guardaron los metadatos (duplicados revisados)",
                             fg=RED_DARK)
            error(self, "No se pudieron guardar los metadatos",
                  f"No se pudo guardar el archivo de metadatos:\n\n{exc}\n\n"
                  "Las marcas de 'no es duplicado' hechas en esta sesión "
                  "pueden perderse si no se soluciona antes de cerrar la "
                  "aplicación.")
            return False

    # -- construcción de la UI (según el perfil) -------------------------------
    def _build_ui(self) -> None:
        if hasattr(self, "root_frame"):
            self.root_frame.destroy()
        self.root_frame = tk.Frame(self, bg=BG)
        self.root_frame.pack(fill="both", expand=True)
        p = self.profile

        header = tk.Frame(self.root_frame, bg=GREEN, height=64)
        header.pack(fill="x")
        header.pack_propagate(False)
        tk.Label(header, text=p.nombre, bg=GREEN, fg=WHITE,
                 font=FONT_TITLE).pack(side="left", padx=22)
        if p.descripcion:
            tk.Label(header, text=p.descripcion, bg=GREEN, fg="#DCEBD6",
                     font=FONT_SMALL).pack(side="left", pady=(4, 0))
        button(header, "🗂 Máquinas", self.on_switch_machine,
              kind="light", small=True,
              tooltip="Ver y elegir entre los documentos de configuración "
                      "de todas las máquinas").pack(side="right", padx=16)
        if len(self._all_profiles) >= 3:
            button(header, "📊 Panel", self.on_panel_multi_maquina,
                  kind="light", small=True,
                  tooltip="Vista consolidada de todas las máquinas: última "
                          "modificación, registros, duplicados y "
                          "alertas de salud").pack(side="right", padx=(0, 4))

        toolbar = tk.Frame(self.root_frame, bg=BG, padx=16, pady=12)
        toolbar.pack(fill="x")

        search_box = tk.Frame(toolbar, bg=WHITE, highlightthickness=1,
                              highlightbackground=BORDER)
        search_box.pack(side="left")
        tk.Label(search_box, text="🔍", bg=WHITE, fg=MUTED, font=FONT).pack(
            side="left", padx=(8, 0))
        self.search_entry = tb.Entry(search_box, textvariable=self.search_var,
                                     font=FONT, width=18, bootstyle="light")
        self.search_entry.pack(side="left", padx=6, pady=6)
        search_hint = tk.Label(search_box, text="Buscar por cualquier dato",
                               bg=WHITE, fg=MUTED, font=FONT_SMALL)
        search_hint.pack(side="left", padx=(0, 8))
        ToolTip(search_box, text="Atajo de teclado: Ctrl+F")

        if any(c.es_numerico for c in p.parametros_visibles()):
            self.filtros_btn = button(toolbar, "▾ Filtros", self.on_filtros, kind="ghost",
                  small=True,
                  tooltip="Filtrar por rango numérico, y guardar combinaciones "
                          "frecuentes de búsqueda + filtros")
            self.filtros_btn.pack(side="left", padx=(6, 0))

        def sep():
            tb.Separator(toolbar, orient="vertical", bootstyle="secondary").pack(
                side="left", fill="y", padx=12, pady=2)

        sep()
        self.new_btn = button(toolbar, "＋ Nuevo", self.on_new, kind="primary",
              tooltip="Agregar un registro nuevo al final (Ctrl+N)")
        self.new_btn.pack(side="left", padx=(0, 6))
        self.edit_btn = button(toolbar, "✎ Editar", self.on_edit, kind="outline",
              tooltip="Modificar el registro seleccionado (doble clic)")
        self.edit_btn.pack(side="left", padx=6)
        self.delete_btn = button(toolbar, "🗑 Eliminar", self.on_delete, kind="danger",
              tooltip="Seleccionar uno o más registros para eliminar")
        self.delete_btn.pack(side="left", padx=6)
        if self.profile.parametros_visibles():
            self.bulk_edit_btn = button(
                toolbar, "✎✎ Editar en masa", self.on_bulk_edit, kind="outline",
                tooltip="Aplicar un mismo valor a todos los registros "
                        "seleccionados (Ctrl+clic o Shift+clic para elegir "
                        "varios)")
            self.bulk_edit_btn.pack(side="left", padx=6)

        sep()
        self.undo_btn = button(toolbar, "↶", self.on_deshacer, kind="ghost", small=True,
              tooltip="Deshacer el último cambio (Ctrl+Z)")
        self.undo_btn.pack(side="left", padx=(0, 2))
        self.redo_btn = button(toolbar, "↷", self.on_rehacer, kind="ghost", small=True,
              tooltip="Rehacer (Ctrl+Y)")
        self.redo_btn.pack(side="left")

        self._toolbar_lock_widgets = [self.new_btn, self.edit_btn, self.delete_btn,
                                       self.search_entry]
        if hasattr(self, "bulk_edit_btn"):
            self._toolbar_lock_widgets.append(self.bulk_edit_btn)

        if p.duplicados_config():
            sep()
            dup_btn = button(toolbar, "⧉ Duplicados", self.on_duplicates, kind="secondary",
                  tooltip="Revisar códigos parecidos y decidir cuáles son "
                          "duplicados reales")
            dup_btn.pack(side="left", padx=(0, 6))
            self._toolbar_lock_widgets.append(dup_btn)
        sep()
        import_btn = button(toolbar, "📥 Importar", self.on_import, kind="secondary",
              tooltip="Comparar contra un Excel y aplicar solo los cambios "
                      "que elijas")
        import_btn.pack(side="left", padx=(0, 6))
        self._toolbar_lock_widgets.append(import_btn)

        self.export_btn = button(toolbar, "📤 Exportar ▾", self._show_export_menu,
                                 kind="secondary",
                                 tooltip="Guardar una copia del archivo en "
                                         "cualquier carpeta de la PC")
        self.export_btn.pack(side="right")
        restore_btn = button(toolbar, "⟲ Restaurar", self.on_restore, kind="outline-danger",
              tooltip="Descartar todos los cambios y volver al archivo "
                      "original")
        restore_btn.pack(side="right", padx=(0, 8))
        backups_btn = button(toolbar, "🕐 Backups", self.on_backups, kind="outline",
              tooltip="Ver puntos de respaldo automáticos y restaurar uno "
                      "en particular")
        backups_btn.pack(side="right", padx=(0, 8))
        historial_btn = button(toolbar, "📜 Historial", self.on_historial, kind="outline",
              tooltip="Ver qué cambió, cuándo y quién lo hizo")
        historial_btn.pack(side="right", padx=(0, 8))
        diffs_btn = button(toolbar, "🔍 Ver cambios", self.on_ver_cambios, kind="outline",
              tooltip="Comparar el archivo actual contra el original, campo "
                      "por campo")
        diffs_btn.pack(side="right", padx=(0, 8))
        salud_btn = button(toolbar, "❤ Salud", self.on_salud, kind="outline",
              tooltip="Ver de una pasada: valores fuera de rango, duplicados "
                      "sin revisar, campos vacíos y slots libres")
        salud_btn.pack(side="right", padx=(0, 8))
        self._toolbar_lock_widgets += [self.export_btn, restore_btn, backups_btn,
                                       historial_btn, diffs_btn, salud_btn]
        self.export_menu = tk.Menu(self, tearoff=0, bg=WHITE, fg=TEXT,
                                   activebackground=GREEN_LIGHT, activeforeground=TEXT,
                                   font=FONT, bd=1, relief="solid")
        self.export_menu.add_command(label="Exportar archivo actual (con cambios)…",
                                     command=lambda: self.on_export("actual"))
        self.export_menu.add_command(label="Exportar archivo original (sin cambios)…",
                                     command=lambda: self.on_export("original"))

        if p.placeholder_regex():
            filt = tk.Frame(self.root_frame, bg=BG, padx=16)
            filt.pack(fill="x")
            tb.Checkbutton(filt, text="Mostrar slots vacíos",
                          variable=self.show_placeholders, command=self.refresh_table,
                          bootstyle="success-round-toggle").pack(side="left")

        # Tabla (columnas dinámicas) con scroll horizontal y vertical
        table_wrap = tk.Frame(self.root_frame, bg=BORDER, padx=1, pady=1)
        table_wrap.pack(fill="both", expand=True, padx=16, pady=(8, 8))

        self._campos = p.campos_visibles()
        cols = ["pos"] + [c.nombre_interno for c in self._campos]
        self.tree = tb.Treeview(table_wrap, columns=cols, show="headings",
                                selectmode="extended", bootstyle="success")
        self.tree.heading("pos", text="#", command=lambda: self._sort_by("pos"))
        self.tree.column("pos", width=60, anchor="center", stretch=False)
        for c in self._campos:
            self.tree.heading(c.nombre_interno, text=c.titulo_ui,
                              command=lambda cc=c.nombre_interno: self._sort_by(cc))
            anchor = "w" if c.es_clave else "center"
            width = 240 if c.es_clave else 130
            self.tree.column(c.nombre_interno, width=width, anchor=anchor,
                             stretch=c.es_clave)
        self.tree.tag_configure("placeholder", foreground=MUTED)
        self.tree.tag_configure("odd", background="#FAFBF9")

        # Scrollbars vertical y horizontal
        vsb = tb.Scrollbar(table_wrap, orient="vertical", command=self.tree.yview,
                          bootstyle="round")
        hsb = tb.Scrollbar(table_wrap, orient="horizontal", command=self.tree.xview,
                          bootstyle="round")
        self.tree.configure(yscrollcommand=vsb.set, xscrollcommand=hsb.set)
        vsb.pack(side="right", fill="y")
        hsb.pack(side="bottom", fill="x")
        self.tree.pack(side="left", fill="both", expand=True)
        self.tree.bind("<Double-1>", self._on_tree_double_click)
        self.tree.bind("<Return>", lambda e: self.on_edit())
        self.tree.bind("<Delete>", lambda e: self._delete_selected_immediate())

        self._delete_footer = tk.Frame(self.root_frame, bg=BG)
        self._delete_footer_label = tk.Label(self._delete_footer, text="", bg=BG,
                                             fg=MUTED, font=FONT_SMALL)
        self._delete_footer_label.pack(side="left")
        button(self._delete_footer, "Aceptar", self._confirm_delete_selection,
              kind="danger").pack(side="right")
        button(self._delete_footer, "Cancelar", self._cancel_delete_mode,
              kind="outline").pack(side="right", padx=(0, 8))

        self.status = tk.Frame(self.root_frame, bg=WHITE, height=30,
                               highlightthickness=1, highlightbackground=BORDER)
        self.status.pack(fill="x", side="bottom")
        self.status.pack_propagate(False)
        self.status_label = tk.Label(self.status, text="", bg=WHITE, fg=MUTED,
                                     font=FONT_SMALL, anchor="w")
        self.status_label.pack(side="left", padx=12)
        self.count_label = tk.Label(self.status, text="", bg=WHITE, fg=GREEN_DARK,
                                    font=FONT_SMALL, anchor="e")
        self.count_label.pack(side="right", padx=12)
        self.version_label = tk.Label(
            self.status, text=f"v{version.version_completa()}", bg=WHITE,
            fg=MUTED, font=FONT_SMALL, anchor="e", cursor="hand2")
        self.version_label.pack(side="right", padx=(0, 4))
        self.version_label.bind("<Button-1>", lambda e: self.on_about())

    # -- tabla -----------------------------------------------------------------
    def _visible_rows(self) -> list[tuple[int, dict]]:
        query = self.search_var.get().strip().lower()
        show_ph = self.show_placeholders.get()
        has_ph = self.profile.placeholder_regex() is not None
        rangos = getattr(self, "_filtros_rango", {})
        out = []
        for i, r in enumerate(self.store.records):
            if has_ph and not show_ph and self.store.is_placeholder(r):
                continue
            if not filtros.coincide_busqueda(r, self._campos, query):
                continue
            if rangos and not filtros.coincide_rangos(r, rangos):
                continue
            out.append((i, r))
        return out

    def refresh_table(self) -> None:
        selected = {int(iid) for iid in self.tree.selection()} \
            if hasattr(self, "tree") else set()
        self.tree.delete(*self.tree.get_children())
        rows = self._visible_rows()

        if self._sort_col and self._sort_col != "pos":
            campo = self.profile.campo_por_nombre(self._sort_col)
            if campo and campo.es_numerico:
                keyf = lambda t: (t[1][self._sort_col] is None, t[1][self._sort_col])
            else:
                keyf = lambda t: str(t[1][self._sort_col]).lower()
            rows.sort(key=keyf, reverse=self._sort_reverse)
        elif self._sort_col == "pos":
            rows.sort(key=lambda t: t[0], reverse=self._sort_reverse)

        for n, (i, r) in enumerate(rows):
            tags = []
            if self.store.is_placeholder(r):
                tags.append("placeholder")
            if n % 2:
                tags.append("odd")
            if self._delete_mode:
                pos_value = "☑" if i in selected else "☐"
            else:
                pos_value = n + 1
            values = [pos_value] + [r[c.nombre_interno] for c in self._campos]
            self.tree.insert("", "end", iid=str(i), tags=tuple(tags), values=values)
        for iid in selected:
            if self.tree.exists(str(iid)):
                self.tree.selection_add(str(iid))
        if self._delete_mode:
            self._update_delete_status()

        total = len(self.store.records)
        shown = len(rows)
        if self.profile.placeholder_regex():
            reales = self.store.count_real()
            self.count_label.config(
                text=f"{shown} mostrados · {reales} reales · {total} slots")
        else:
            self.count_label.config(text=f"{shown} mostrados · {total} registros")

    def _sort_by(self, col: str) -> None:
        if self._sort_col == col:
            self._sort_reverse = not self._sort_reverse
        else:
            self._sort_col, self._sort_reverse = col, False
        self._update_sort_headers()
        self.refresh_table()

    def _update_sort_headers(self) -> None:
        arrow = " ▼" if self._sort_reverse else " ▲"
        if not self._delete_mode:
            pos_text = "#" + arrow if self._sort_col == "pos" else "#"
            self.tree.heading("pos", text=pos_text)
        for c in self._campos:
            label = c.titulo_ui + (arrow if self._sort_col == c.nombre_interno else "")
            self.tree.heading(c.nombre_interno, text=label)

    def ir_a_registro(self, code: str) -> None:
        """Salta a un registro por código desde otra ventana (p. ej. el
        panel de salud): limpia cualquier filtro que lo esté ocultando,
        muestra placeholders si hace falta, y lo selecciona/enfoca en la
        tabla principal."""
        idx = self.store.find_key(code)
        if idx == -1:
            return
        if self.store.is_placeholder(self.store.records[idx]):
            self.show_placeholders.set(True)
        self.search_var.set("")
        self.refresh_table()
        if self.tree.exists(str(idx)):
            self.tree.selection_set(str(idx))
            self.tree.see(str(idx))
            self.tree.focus(str(idx))

    def _selected_index(self) -> int | None:
        sel = self.tree.selection()
        return int(sel[0]) if sel else None

    def _set_status(self, text: str, fg: str = MUTED) -> None:
        self.status_label.config(text=text, fg=fg)

    # -- acciones --------------------------------------------------------------
    def on_new(self) -> None:
        dlg = RecordDialog(self, self.store, "Nuevo registro")
        if dlg.result:
            self.store.add(dlg.result)
            guardado_ok = self._autosave()
            self.refresh_table()
            new_index = len(self.store.records) - 1
            if self.tree.exists(str(new_index)):
                self.tree.selection_set(str(new_index))
                self.tree.see(str(new_index))
            code = self.store.key_of(dlg.result)
            if guardado_ok:
                self._registrar_cambios(f"alta de «{code}»",
                                       [CambioRegistro("alta", code, nuevos=dict(dlg.result))])
                toast(self, f"Registro «{code}» agregado.")

    # -- edición en línea (Nivel 4.8) -------------------------------------------
    def _on_tree_double_click(self, event) -> None:
        """Doble clic sobre una celda de PARÁMETRO edita esa celda sola, sin
        abrir el diálogo completo. Sobre la clave (o en modo eliminación,
        o fuera de una celda de datos) se abre el diálogo de siempre — la
        clave puede afectar duplicados/sidecar y no vale la pena
        duplicar esa lógica acá."""
        if self._delete_mode:
            return
        if self.tree.identify("region", event.x, event.y) != "cell":
            return
        row_iid = self.tree.identify_row(event.y)
        col_id = self.tree.identify_column(event.x)
        if not row_iid or not col_id:
            return
        cols = ["pos"] + [c.nombre_interno for c in self._campos]
        try:
            col_index = int(col_id[1:]) - 1
        except ValueError:
            return
        if col_index < 0 or col_index >= len(cols) or cols[col_index] == "pos":
            self.on_edit()
            return
        campo = self.profile.campo_por_nombre(cols[col_index])
        if campo is None or campo.es_clave:
            self.on_edit()
            return
        self._editar_celda(int(row_iid), campo, col_id)

    def _editar_celda(self, idx: int, campo: Campo, col_id: str) -> None:
        bbox = self.tree.bbox(str(idx), col_id)
        if not bbox:
            return
        x, y, w, h = bbox
        valor_actual = self.store.records[idx].get(campo.nombre_interno, "")
        var = tk.StringVar(value=str(valor_actual))
        entry = tb.Entry(self.tree, textvariable=var, font=FONT, bootstyle="success")
        entry.place(x=x, y=y, width=w, height=h)
        entry.select_range(0, "end")
        entry.focus_set()

        def finalizar(guardar: bool) -> None:
            if not entry.winfo_exists():
                return
            entry.unbind("<FocusOut>")
            texto = var.get()
            entry.destroy()
            if not guardar or texto.strip() == str(valor_actual).strip():
                return
            valor, error = validacion.parsear_valor_campo(campo, texto)
            if error:
                warn(self, "No se guardó el cambio", error)
                return
            self._aplicar_edicion_celda(idx, campo, valor)

        entry.bind("<Return>", lambda e: finalizar(True))
        entry.bind("<Escape>", lambda e: finalizar(False))
        entry.bind("<FocusOut>", lambda e: finalizar(True))

    def _aplicar_edicion_celda(self, idx: int, campo: Campo, valor) -> None:
        anterior = dict(self.store.records[idx])
        self.store.update(idx, {campo.nombre_interno: valor})
        nuevo = dict(self.store.records[idx])
        guardado_ok = self._autosave()
        self.refresh_table()
        if self.tree.exists(str(idx)):
            self.tree.selection_set(str(idx))
        if guardado_ok:
            self._registrar_cambios(
                f"edición en línea de «{self.store.key_of(nuevo)}»",
                [CambioRegistro("modificacion", self.store.key_of(nuevo),
                                anteriores=anterior, nuevos=nuevo)])

    def on_edit(self) -> None:
        idx = self._selected_index()
        if idx is None:
            info(self, "Editar", "Seleccioná un registro para editar.")
            return
        old_key = self.store.key_of(self.store.records[idx])
        registro_anterior = dict(self.store.records[idx])
        dlg = RecordDialog(self, self.store, "Modificar registro",
                           record=self.store.records[idx], edit_index=idx)
        if dlg.result:
            self.store.update(idx, dlg.result)
            new_key = self.store.key_of(self.store.records[idx])
            if new_key != old_key:
                self.sidecar.rename_key(old_key, new_key)
                self._guardar_sidecar()
            guardado_ok = self._autosave()
            self.refresh_table()
            if self.tree.exists(str(idx)):
                self.tree.selection_set(str(idx))
            if guardado_ok:
                self._registrar_cambios(
                    f"modificación de «{new_key}»",
                    [CambioRegistro("modificacion", new_key, anteriores=registro_anterior,
                                    nuevos=dict(self.store.records[idx]))])
                toast(self, f"Registro «{new_key}» modificado.")

    def on_bulk_edit(self) -> None:
        if self._delete_mode:
            return
        sel = self.tree.selection()
        if len(sel) < 2:
            info(self, "Editar en masa",
                "Seleccioná dos o más registros (Ctrl+clic o Shift+clic) para "
                "aplicarles el mismo valor de una vez. Para uno solo, usá "
                "«Editar» o doble clic en la celda.")
            return
        indices = sorted(int(iid) for iid in sel)
        BulkEditDialog(self, self, indices)

    def on_delete(self) -> None:
        self._enter_delete_mode()

    def _delete_selected_immediate(self) -> None:
        """Atajo de teclado (tecla Supr) usando la selección actual del tree."""
        if self._delete_mode:
            return
        sel = self.tree.selection()
        if not sel:
            info(self, "Eliminar", "Seleccioná uno o más registros.")
            return
        self._delete_indices(sorted((int(iid) for iid in sel), reverse=True))

    def _delete_indices(self, indices: list[int]) -> None:
        codes = [self.store.key_of(self.store.records[i]) for i in indices]
        preview = ", ".join(codes[:5]) + (" …" if len(codes) > 5 else "")
        if not confirm(self, "Confirmar eliminación",
                       f"¿Eliminar {len(indices)} registro(s)?\n\n{preview}"):
            return
        eliminados = [(self.store.key_of(self.store.records[i]), dict(self.store.records[i]))
                     for i in indices]
        for i in indices:
            self.store.delete(i)
        guardado_ok = self._autosave()
        self.refresh_table()
        if guardado_ok:
            cambios = [CambioRegistro("baja", code, anteriores=registro)
                      for code, registro in eliminados]
            descripcion = (f"baja de «{eliminados[0][0]}»" if len(eliminados) == 1
                          else f"baja de {len(eliminados)} registros")
            self._registrar_cambios(descripcion, cambios)
            toast(self, f"{len(indices)} registro(s) eliminado(s).", kind="warning")

    def _enter_delete_mode(self) -> None:
        if self._delete_mode:
            return
        self._delete_mode = True
        self.tree.selection_remove(*self.tree.selection())
        self.tree.heading("pos", text="")
        self.tree.bind("<Button-1>", self._on_row_click_delete_mode)
        self.bind("<Escape>", lambda e: self._cancel_delete_mode())
        for w in self._toolbar_lock_widgets:
            w.config(state="disabled")
        self.undo_btn.config(state="disabled")
        self.redo_btn.config(state="disabled")
        self._delete_footer.pack(fill="x", padx=16, pady=(0, 8), before=self.status)
        self.refresh_table()

    def _exit_delete_mode(self) -> None:
        if not self._delete_mode:
            return
        self._delete_mode = False
        self.tree.unbind("<Button-1>")
        self.tree.heading("pos", text="#", command=lambda: self._sort_by("pos"))
        self.tree.selection_remove(*self.tree.selection())
        self.unbind("<Escape>")
        for w in self._toolbar_lock_widgets:
            w.config(state="normal")
        self._actualizar_botones_deshacer()
        self._delete_footer.pack_forget()
        self.refresh_table()

    def _on_row_click_delete_mode(self, event) -> "str | None":
        row = self.tree.identify_row(event.y)
        if not row:
            return None
        if row in self.tree.selection():
            self.tree.selection_remove(row)
        else:
            self.tree.selection_add(row)
        self.refresh_table()
        return "break"

    def _update_delete_status(self) -> None:
        n = len(self.tree.selection())
        self._delete_footer_label.config(
            text=f"{n} registro(s) seleccionado(s)" if n else
                 "Marcá los registros a eliminar (tocá la fila).")

    def _confirm_delete_selection(self) -> None:
        sel = self.tree.selection()
        if not sel:
            info(self, "Eliminar", "Seleccioná uno o más registros.")
            return
        indices = sorted((int(iid) for iid in sel), reverse=True)
        self._exit_delete_mode()
        self._delete_indices(indices)

    def _cancel_delete_mode(self) -> None:
        self._exit_delete_mode()

    def on_duplicates(self) -> None:
        dlg = DuplicatesDialog(self, self.store, self.sidecar)
        sidecar_ok = True
        if dlg.reviewed_any:
            sidecar_ok = self._guardar_sidecar()
        if dlg.deleted_any or dlg.reviewed_any:
            guardado_ok = True
            if dlg.deleted_any:
                guardado_ok = self._autosave()
            self.refresh_table()
            if guardado_ok and sidecar_ok:
                if dlg.deleted_any:
                    cambios = [CambioRegistro("baja", self.store.key_of(registro),
                                              anteriores=registro)
                              for registro in dlg.eliminados]
                    self._registrar_cambios(
                        f"baja de {len(cambios)} duplicado(s)", cambios, origen="duplicados")
                toast(self, "Duplicados eliminados." if dlg.deleted_any
                      else "Revisión de duplicados guardada.")

    def on_import(self) -> None:
        if excel_import is None:
            error(self, "Falta un componente",
                 "No se pudo cargar el módulo de importación.")
            return
        path = filedialog.askopenfilename(
            title="Importar cambios desde Excel o CSV",
            filetypes=[("Excel o CSV", "*.xlsx *.xlsm *.csv"),
                       ("Excel", "*.xlsx *.xlsm"), ("CSV", "*.csv"),
                       ("Todos los archivos", "*.*")])
        if not path:
            return
        try:
            workbook = excel_import.abrir_archivo_importacion(path)
        except Exception as exc:
            error(self, "Error al abrir el archivo", f"No se pudo leer:\n\n{exc}")
            return
        nombre_archivo = os.path.basename(path)
        log_config.get_logger().info("Importación iniciada desde: %s", path)
        try:
            dlg = ImportDialog(self, self.store, workbook, nombre_archivo, self.data_dir)
        finally:
            workbook.close()
        if dlg.applied_any:
            guardado_ok = self._autosave()
            self.refresh_table()
            if guardado_ok:
                origen = f"excel:{nombre_archivo}"
                cambios = []
                for d in dlg.applied_diffs:
                    nuevos = {**d["old_completo"],
                             **{f: v for f, v in d["new"].items() if v is not None}}
                    cambios.append(CambioRegistro("modificacion", d["code"],
                                                  anteriores=d["old_completo"], nuevos=nuevos))
                for d in dlg.applied_new:
                    cambios.append(CambioRegistro("alta", d["code"], nuevos=dict(d["valores"])))
                for d in dlg.applied_obsolete:
                    cambios.append(CambioRegistro("baja", d["code"], anteriores=d["registro"]))
                self._registrar_cambios(f"importación de {nombre_archivo}", cambios, origen=origen)
                toast(self, "Cambios importados según tu selección.")

    def on_restore(self) -> None:
        if not confirm(self, "Restaurar original",
                       "Se descartarán TODOS los cambios y se volverá al "
                       "archivo original.\n\n¿Continuar?"):
            return
        try:
            copiar_atomico(self.path_original, self.path_actual)
            nuevo_store = DataStore.load(self.path_actual, self.profile)
        except (OSError, ValueError, UnicodeDecodeError, LookupError) as exc:
            error(self, "No se pudo restaurar",
                 f"No se pudo restaurar el archivo original:\n\n{exc}\n\n"
                 "Los datos actuales NO se modificaron.")
            return
        self.store = nuevo_store
        self._hash_conocido = deteccion_externa.hash_archivo(self.path_actual)
        # Restaurar el original invalida cualquier deshacer/rehacer pendiente:
        # los registros que esos comandos referencian pueden ya ni existir.
        self._pila_deshacer.clear()
        self._pila_rehacer.clear()
        self._actualizar_botones_deshacer()
        self.refresh_table()
        self._registrar_evento("restauracion", "*",
                              nuevos={"registros": len(self.store.records)},
                              origen="restaurar_original")
        toast(self, "Archivo restaurado al original.", kind="warning")

    def on_backups(self) -> None:
        dlg = BackupsDialog(self, self.data_dir, self.path_actual, self.profile, self.store)
        if dlg.restaurado:
            self._recargar_tras_restaurar_backup()

    def on_historial(self) -> None:
        dlg = HistorialDialog(self, self.path_historial, self.data_dir,
                              self.path_actual, self.profile, self.store)
        if dlg.restaurado:
            self._recargar_tras_restaurar_backup()

    def on_ver_cambios(self) -> None:
        try:
            store_original = DataStore.load(self.path_original, self.profile)
        except (OSError, ValueError, UnicodeDecodeError, LookupError) as exc:
            error(self, "No se pudo leer el original",
                 f"No se pudo leer el archivo original para comparar:\n\n{exc}")
            return
        DiffsDialog(self, self.store, store_original)

    def on_salud(self) -> None:
        hallazgos = salud.evaluar_salud(self.store, self.sidecar)
        SaludDialog(self, self.store, hallazgos)

    def on_filtros(self) -> None:
        FiltrosDialog(self, self)

    def on_about(self) -> None:
        info(self, "Acerca de",
            f"{APP_TITLE}\n\n"
            f"Versión: {version.APP_VERSION}\n"
            f"Compilación: {version.FECHA_COMPILACION}\n"
            f"Máquina activa: {self.profile.nombre}\n\n"
            f"Registro de diagnóstico: {log_config.log_dir()}")

    def _recargar_tras_restaurar_backup(self) -> None:
        try:
            nuevo_store = DataStore.load(self.path_actual, self.profile)
        except (OSError, ValueError, UnicodeDecodeError, LookupError) as exc:
            error(self, "Backup restaurado, pero no se pudo releer",
                 f"El archivo se restauró, pero no se pudo volver a "
                 f"cargar:\n\n{exc}")
            return
        self.store = nuevo_store
        self._hash_conocido = deteccion_externa.hash_archivo(self.path_actual)
        self._pila_deshacer.clear()
        self._pila_rehacer.clear()
        self._actualizar_botones_deshacer()
        self.refresh_table()
        self._registrar_evento("restauracion", "*",
                              nuevos={"registros": len(self.store.records)},
                              origen="restaurar_backup")
        toast(self, "Backup restaurado.", kind="warning")

    def on_panel_multi_maquina(self) -> None:
        self._reload_all_profiles()
        PanelMultiMaquinaDialog(self, self)

    def on_switch_machine(self) -> None:
        sel = MachineSelector(self, self._all_profiles, current_id=self.profile.id)
        edited_active = sel.edited_id and sel.edited_id == self.profile.id
        self._reload_all_profiles()

        if sel.result and sel.result.id != self.profile.id:
            # El usuario eligió administrar otra máquina (o acaba de crear
            # una y quedó elegida): activarla, usando la versión recién
            # releída de disco si está (por si además se editó algo más).
            actualizado = next((p for p in self._all_profiles if p.id == sel.result.id),
                               sel.result)
            self._activate_profile(actualizado)
            toast(self, f"Ahora administrando: {self.profile.nombre}")
        elif edited_active:
            # Se editó el formato de la máquina que ya estaba activa:
            # recargarla en caliente para reflejar el nuevo esquema.
            actualizado = next((p for p in self._all_profiles if p.id == self.profile.id),
                               self.profile)
            self._activate_profile(actualizado)
            toast(self, "Formato de la máquina actualizado.")

    def _show_export_menu(self) -> None:
        x = self.export_btn.winfo_rootx()
        y = self.export_btn.winfo_rooty() + self.export_btn.winfo_height()
        self.export_menu.tk_popup(x, y)

    def on_export(self, which: str) -> None:
        label = "actual (con cambios)" if which == "actual" else "original (sin cambios)"
        ext = self.profile.extension
        dest = filedialog.asksaveasfilename(
            title=f"Exportar archivo {label}", defaultextension=f".{ext}",
            initialfile=f"{self.profile.archivo_inicial or ('export.' + ext)}",
            filetypes=[(f"Archivo {ext.upper()}", f"*.{ext}"),
                       ("Todos los archivos", "*.*")])
        if not dest:
            return
        try:
            if which == "actual":
                self.store.save(self.path_actual)
                self._hash_conocido = deteccion_externa.hash_archivo(self.path_actual)
                copiar_atomico(self.path_actual, dest)
            else:
                copiar_atomico(self.path_original, dest)
        except OSError as exc:
            log_config.get_logger().error("Exportación falló hacia %s: %s", dest, exc)
            error(self, "Error al exportar", str(exc))
            return
        log_config.get_logger().info("Exportado (%s) a: %s", which, dest)
        self._set_status(f"Exportado a: {dest}")
        toast(self, f"Exportado a {os.path.basename(dest)}")


# ============================================================================
def _cargar_perfiles():
    carpeta = paths.profiles_dir()
    perfiles = []
    errores = []
    for name in sorted(os.listdir(carpeta)):
        if not name.endswith(".json"):
            continue
        try:
            perfiles.append(Profile.load(os.path.join(carpeta, name)))
        except ProfileError as exc:
            errores.append(f"{name}: {exc}")
    return perfiles, errores


def _mostrar_dialogo_excepcion(detalle: str) -> None:
    """Diálogo para una excepción no capturada: en vez del traceback crudo
    de Tkinter en la consola, muestra el error, la ruta del log, y un botón
    para copiar el detalle completo al portapapeles."""
    top = tk.Toplevel()
    top.title("Error inesperado")
    top.configure(bg=PANEL)
    top.geometry("620x420")
    tk.Label(top, text="Ocurrió un error inesperado", bg=PANEL, fg=RED_DARK,
             font=FONT_BOLD, anchor="w").pack(fill="x", padx=16, pady=(14, 4))
    tk.Label(top, text=f"El detalle quedó guardado en: {log_config.log_dir()}",
             bg=PANEL, fg=MUTED, font=FONT_SMALL, anchor="w",
             wraplength=580, justify="left").pack(fill="x", padx=16)
    text = tk.Text(top, wrap="word", height=14, font=("Consolas", 9))
    text.insert("1.0", detalle)
    text.configure(state="disabled")
    text.pack(fill="both", expand=True, padx=16, pady=10)
    footer = tk.Frame(top, bg=PANEL)
    footer.pack(fill="x", padx=16, pady=(0, 14))

    def _copiar():
        top.clipboard_clear()
        top.clipboard_append(detalle)

    button(footer, "Copiar detalle", _copiar, kind="secondary").pack(side="right")
    button(footer, "Cerrar", top.destroy, kind="primary").pack(side="right", padx=(0, 10))
    top.transient()
    top.grab_set()


def main() -> None:
    logger = log_config.configurar_logging()
    logger.info("Arranque — versión %s", version.version_completa())
    log_config.instalar_manejador_excepciones_no_capturadas(_mostrar_dialogo_excepcion)

    enable_dpi_awareness()
    perfiles, errores = _cargar_perfiles()
    if not perfiles:
        root = tk.Tk()
        root.withdraw()
        detalle = ("\n\n" + "\n".join(errores)) if errores else ""
        from tkinter import messagebox
        messagebox.showerror(
            "Sin perfiles",
            "No se encontró ningún perfil de máquina válido en la carpeta "
            "'profiles'." + detalle)
        logger.error("Sin perfiles válidos al arrancar.%s", detalle)
        return
    app = App(perfiles)
    app.mainloop()
    logger.info("Cierre de la aplicación.")


if __name__ == "__main__":
    main()
