#!/usr/bin/env python3
"""Static checks for the Angular sources that do not need node_modules.

Catches two classes of failure that only surface at build time:

1. **Template literals that close early.** A stray backtick inside a
   ``template:`` block terminates the string, so the rest of the markup becomes
   further arguments to ``@Component`` — Angular reports this as NG1002. Simply
   counting backticks for balance does not catch it: a *pair* of stray backticks
   keeps the total even while still breaking the decorator.

2. **Unresolvable internal imports**, including the path aliases.

Run: ``python scripts/check_frontend.py``
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent / "frontend" / "src"
ALIASES = {
    "@core/": "app/core/",
    "@features/": "app/features/",
    "@shared/": "app/shared/",
    "@env/": "environments/",
}


def _closes_early(text: str, opener: re.Match[str]) -> int | None:
    """Return the 1-based line where the literal ends, if it ends too soon."""
    index = opener.end()
    while index < len(text):
        if text[index] == "\\":
            index += 2
            continue
        if text[index] == "`":
            break
        index += 1

    tail = text[index + 1 : index + 40].lstrip()
    if tail.startswith((",", "}", "]")):
        return None
    return text[:index].count("\n") + 1


def check_decorator_literals() -> list[str]:
    problems: list[str] = []
    for path in sorted(ROOT.rglob("*.ts")):
        text = path.read_text()
        for pattern in (r"template:\s*`", r"styles:\s*\[\s*`"):
            for match in re.finditer(pattern, text):
                line = _closes_early(text, match)
                if line is not None:
                    kind = "template" if "template" in pattern else "styles"
                    problems.append(
                        f"{path.relative_to(ROOT)}:{line}: {kind} literal closes "
                        "early — a stray backtick inside the block ends the "
                        "string (Angular reports NG1002)"
                    )
    return problems


def check_imports() -> list[str]:
    problems: list[str] = []
    for path in sorted(ROOT.rglob("*.ts")):
        text = path.read_text()

        for alias, target in ALIASES.items():
            for match in re.finditer(rf"from '{re.escape(alias)}([^']+)'", text):
                if not (ROOT / target / f"{match.group(1)}.ts").exists():
                    problems.append(
                        f"{path.relative_to(ROOT)}: unresolved {alias}{match.group(1)}"
                    )

        for match in re.finditer(r"from '(\.[^']+)'", text):
            spec = match.group(1)
            if not (path.parent / f"{spec}.ts").exists() and not (
                path.parent / spec / "index.ts"
            ).exists():
                problems.append(f"{path.relative_to(ROOT)}: unresolved {spec}")

    return problems


def main() -> int:
    files = list(ROOT.rglob("*.ts"))
    problems = check_decorator_literals() + check_imports()

    if problems:
        print(f"✗ {len(problems)} problem(s) across {len(files)} TypeScript files:\n")
        for problem in problems:
            print(f"  {problem}")
        return 1

    print(f"✓ {len(files)} TypeScript files: decorator literals and imports are sound")
    return 0


if __name__ == "__main__":
    sys.exit(main())
