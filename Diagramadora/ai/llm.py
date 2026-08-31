"""
Motor de IA LOCAL (llama.cpp) - corre 100% dentro de la maquina.

No usa internet, no usa API keys, no manda datos a ningun lado.

La confiabilidad no se apoya en que el modelo "se porte bien": se le impone una
GRAMATICA (GBNF) que lo obliga a responder exactamente con la estructura pedida.
El modelo solo puede elegir el TEXTO de las etiquetas; las claves y el formato
JSON los fija la gramatica. Por eso un modelo chico (1.5B) alcanza para esto.
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from dataclasses import dataclass
from typing import Optional


def _base_dir() -> str:
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def runtime_dir() -> str:
    """Ubica la carpeta 'runtime' (motor de IA + modelo).

    Se busca en varios lugares para que funcione tanto ejecutando el codigo
    fuente como el .exe, y sin tener que duplicar el modelo (que pesa 1 GB).
    """
    base = _base_dir()
    candidates = [
        os.path.join(base, "runtime"),
        os.path.join(os.path.dirname(base), "runtime"),
        os.path.join(os.getcwd(), "runtime"),
    ]
    for c in candidates:
        if os.path.isdir(c):
            return c
    return candidates[0]


def find_llama_cli() -> Optional[str]:
    """Ubica el ejecutable de generacion.

    En las versiones nuevas de llama.cpp la generacion cruda (la que acepta
    gramatica y no arranca un chat interactivo) esta en llama-completion.exe;
    en las viejas estaba en llama-cli.exe.
    """
    folder = os.path.join(runtime_dir(), "llama")
    for name in ("llama-completion.exe", "llama-cli.exe"):
        exe = os.path.join(folder, name)
        if os.path.isfile(exe):
            return exe
    return None


ANSI_RE = re.compile(r"\x1b\[[0-9;]*[A-Za-z]")


def _clean_output(text: str) -> str:
    text = ANSI_RE.sub("", text)
    text = text.replace("[end of text]", "")
    return text.strip()


def find_model() -> Optional[str]:
    models = os.path.join(runtime_dir(), "models")
    if not os.path.isdir(models):
        return None
    ggufs = [f for f in os.listdir(models) if f.lower().endswith(".gguf")]
    if not ggufs:
        return None
    # el mas grande suele ser el mejor disponible
    ggufs.sort(key=lambda f: os.path.getsize(os.path.join(models, f)), reverse=True)
    return os.path.join(models, ggufs[0])


def is_available() -> tuple[bool, str]:
    """Indica si la IA local se puede usar, y si no, por que."""
    if find_llama_cli() is None:
        return False, "No se encontro el motor de IA (runtime/llama/llama-cli.exe)."
    model = find_model()
    if model is None:
        return False, "No se encontro ningun modelo .gguf en runtime/models/."
    return True, f"IA local lista ({os.path.basename(model)})"


# ---------------------------------------------------------------------------
# Gramatica GBNF
# ---------------------------------------------------------------------------


def _gbnf_escape(text: str) -> str:
    return text.replace("\\", "\\\\").replace('"', '\\"')


def build_labeling_grammar(keys: list[str]) -> str:
    """Genera una gramatica que obliga a describir EXACTAMENTE estas claves, en orden.

    El modelo no puede inventar claves, ni saltearse ninguna, ni romper el JSON:
    lo unico libre es el texto de 'label' y 'unit'.
    """
    lines = ["root ::= \"[\" " + " \",\" ".join(f"e{i}" for i in range(len(keys))) + " \"]\""]
    for i, k in enumerate(keys):
        esc = _gbnf_escape(k)
        lines.append(
            f'e{i} ::= "{{\\"key\\": \\"{esc}\\", \\"label\\": " str ", \\"unit\\": " str "}}"'
        )
    # char{0,48}: permite tambien la cadena vacia "", que es la respuesta
    # correcta cuando un campo no tiene unidad de medida.
    lines.append('str ::= "\\"" char{0,48} "\\""')
    lines.append('char ::= [^"\\\\\\n]')
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Ejecucion
# ---------------------------------------------------------------------------

CHATML = (
    "<|im_start|>system\n{system}<|im_end|>\n"
    "<|im_start|>user\n{user}<|im_end|>\n"
    "<|im_start|>assistant\n"
)


@dataclass
class LlmResult:
    ok: bool
    text: str
    error: str = ""
    seconds: float = 0.0


def run_llm(
    system: str,
    user: str,
    grammar: Optional[str] = None,
    max_tokens: int = 768,
    threads: int = 4,
    ctx: int = 8192,
    timeout: int = 900,
    workdir: Optional[str] = None,
    progress_callback=None,
) -> LlmResult:
    """Ejecuta el modelo local una vez y devuelve el texto generado."""
    import time

    cli = find_llama_cli()
    model = find_model()
    if cli is None or model is None:
        return LlmResult(False, "", "IA local no disponible.")

    workdir = workdir or os.path.join(runtime_dir(), "tmp")
    os.makedirs(workdir, exist_ok=True)

    prompt = CHATML.format(system=system, user=user)
    prompt_file = os.path.join(workdir, "prompt.txt")
    with open(prompt_file, "w", encoding="utf-8") as f:
        f.write(prompt)

    cmd = [
        cli,
        "-m", model,
        "-f", prompt_file,
        "-n", str(max_tokens),
        "-c", str(ctx),
        "-t", str(threads),
        "--temp", "0",
        "-no-cnv",
        "--no-display-prompt",
        "--no-warmup",
    ]

    grammar_file = None
    if grammar:
        grammar_file = os.path.join(workdir, "grammar.gbnf")
        with open(grammar_file, "w", encoding="utf-8") as f:
            f.write(grammar)
        cmd += ["--grammar-file", grammar_file]

    creationflags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0

    t0 = time.time()
    try:
        proc = subprocess.run(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
            creationflags=creationflags,
        )
    except subprocess.TimeoutExpired:
        return LlmResult(False, "", f"La IA local tardo mas de {timeout}s y se cancelo.",
                         time.time() - t0)
    except FileNotFoundError:
        return LlmResult(False, "", "No se pudo ejecutar llama-cli.exe.")
    except Exception as exc:  # noqa: BLE001
        return LlmResult(False, "", f"Error ejecutando la IA local: {exc}")

    elapsed = time.time() - t0
    if proc.returncode != 0:
        detail = (proc.stderr or "").strip().splitlines()
        tail = detail[-1] if detail else f"codigo {proc.returncode}"
        return LlmResult(False, _clean_output(proc.stdout or ""),
                         f"El motor de IA fallo: {tail}", elapsed)
    return LlmResult(True, _clean_output(proc.stdout or ""), "", elapsed)


def extract_json(text: str):
    """Recupera el primer JSON valido del texto generado."""
    text = text.strip()
    for opener, closer in (("[", "]"), ("{", "}")):
        start = text.find(opener)
        if start == -1:
            continue
        depth = 0
        for i in range(start, len(text)):
            if text[i] == opener:
                depth += 1
            elif text[i] == closer:
                depth -= 1
                if depth == 0:
                    try:
                        return json.loads(text[start:i + 1])
                    except json.JSONDecodeError:
                        break
    return None
