"""
config_loader.py — Lee config.md y expone los parámetros del proyecto como un objeto.

config.md usa líneas del tipo `- `clave`: valor` dentro de secciones ## .
Este parser es intencionalmente simple (regex sobre líneas), NO un parser de Markdown
genérico. Si cambias el formato de config.md, ajusta el regex de abajo.
"""
from __future__ import annotations

import ast
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

_LINE_RE = re.compile(r"^\s*-\s*`([^`]+)`\s*:\s*(.+?)\s*$")


def _coerce(raw: str) -> Any:
    """Convierte el string crudo del value a int/float/list/str según corresponda."""
    raw = raw.strip()
    # quitar comentarios inline tipo "# opciones: ..."
    raw = re.split(r"\s+#", raw)[0].strip()
    if raw == "":
        return None
    # listas tipo ["A", "B"]
    if raw.startswith("[") and raw.endswith("]"):
        try:
            return ast.literal_eval(raw)
        except (ValueError, SyntaxError):
            return raw
    # números
    try:
        if "." in raw:
            return float(raw)
        return int(raw)
    except ValueError:
        pass
    return raw.strip('"').strip("'")


@dataclass
class Config:
    values: dict[str, Any] = field(default_factory=dict)

    def __getattr__(self, item: str) -> Any:
        try:
            return self.values[item]
        except KeyError as exc:
            raise AttributeError(f"config.md no define la clave '{item}'") from exc

    def get(self, item: str, default: Any = None) -> Any:
        return self.values.get(item, default)


def load_config(path: str | Path = "config.md") -> Config:
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"No se encontró {path}. Ejecuta desde la raíz del repo.")

    values: dict[str, Any] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        m = _LINE_RE.match(line)
        if not m:
            continue
        key, raw_value = m.group(1), m.group(2)
        values[key] = _coerce(raw_value)

    if not values:
        raise ValueError(
            "config.md no produjo ningún parámetro. Revisa que las líneas sigan "
            "el formato '- `clave`: valor'."
        )
    return Config(values=values)


if __name__ == "__main__":
    cfg = load_config()
    for k, v in cfg.values.items():
        print(f"{k!r:35s} -> {v!r}")
