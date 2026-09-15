"""
fix_encoding_csv.py
====================
Arregla un CSV que tiene caracteres ilegibles en UTF-8 (mojibake): los
decodifica probando encodings alternativos (cp1252, latin-1— los mismos que
usa `app/ai/structure.py` para leer archivos de mediciones) y vuelve a
guardarlos como UTF-8 limpio.

Uso:
    python fix_encoding_csv.py "ruta\\al\\archivo.csv" [salida.csv]

Si no se indica archivo de salida, escribe "<nombre>_utf8.csv" al lado del
original (no pisa el archivo original).
"""
from __future__ import annotations

import sys
import unicodedata
from pathlib import Path


def leer_tolerante(path: Path) -> tuple[str, str]:
    """Decodifica probando encodings en orden; devuelve (texto, encoding_usado)."""
    data = path.read_bytes()
    for enc in ("utf-8-sig", "cp1252", "latin-1"):
        try:
            return data.decode(enc), enc
        except UnicodeDecodeError:
            continue
    return data.decode("latin-1", errors="replace"), "latin-1 (con reemplazos)"


def normalizar(texto: str) -> str:
    """Reduce cualquier caracter Unicode 'raro' que no sea el set esperado en
    estos exports (ASCII + tildes/ñ en español) a su forma sin diacríticos,
    p. ej. 'ö' -> 'o', para corregir corrupciones tipo 'PESADÖ' -> 'PESADO'
    sin tocar acentos legítimos del español."""
    letras_espanol = set("áéíóúñÁÉÍÓÚÑüÜ¿¡")
    out = []
    for ch in texto:
        if ch in letras_espanol or ord(ch) < 128:
            out.append(ch)
            continue
        base = "".join(
            c for c in unicodedata.normalize("NFKD", ch) if not unicodedata.combining(c)
        )
        out.append(base if base else ch)
    return "".join(out)


def main(argv: list[str]) -> int:
    if not argv:
        print("Uso: python fix_encoding_csv.py <archivo.csv> [salida.csv]")
        return 1

    entrada = Path(argv[0])
    salida = Path(argv[1]) if len(argv) > 1 else entrada.with_name(
        entrada.stem + "_utf8" + entrada.suffix
    )

    texto, encoding_usado = leer_tolerante(entrada)
    texto_limpio = normalizar(texto)

    cambios = sum(1 for a, b in zip(texto, texto_limpio) if a != b)
    salida.write_text(texto_limpio, encoding="utf-8-sig", newline="")

    print(f"Leído como: {encoding_usado}")
    print(f"Caracteres corregidos: {cambios}")
    print(f"Guardado en: {salida}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
