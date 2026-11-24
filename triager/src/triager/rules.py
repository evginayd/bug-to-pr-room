"""Business rules of the demo app, read from the docstring of its main module.

The docstring is the spec the agents check behaviour against, so the Triager
reads it from the code instead of keeping its own copy.
"""

from __future__ import annotations

import ast
from pathlib import Path

HEADING = "Business rules"


def load_rules(main_py: Path) -> list[str]:
    """Return the bullet points under "Business rules" in the module docstring."""
    tree = ast.parse(main_py.read_text(encoding="utf-8"))
    doc = ast.get_docstring(tree) or ""
    rules: list[str] = []
    in_section = False
    for line in doc.splitlines():
        stripped = line.strip()
        if stripped.startswith(HEADING):
            in_section = True
            continue
        if not in_section:
            continue
        if stripped.startswith("- "):
            rules.append(stripped[2:].strip())
        elif rules and stripped and not line.startswith(" "):
            break  # next paragraph
        elif rules and stripped:
            rules[-1] += " " + stripped  # wrapped bullet
    return rules
