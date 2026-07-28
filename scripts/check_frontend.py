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

PROJECT = Path(__file__).resolve().parent.parent
ROOT = PROJECT / "frontend" / "src"
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


#: TypeScript request interfaces and the Pydantic models they must mirror.
#: A field added on one side and forgotten on the other is a build error at best
#: and a silently dropped parameter at worst.
CONTRACTS = {
    "RunExecutionPayload": "RunExecutionIn",
}


def check_request_contracts() -> list[str]:
    """Compare each TypeScript request type against its Pydantic counterpart."""
    import ast

    backend = PROJECT / "backend" / "app" / "schemas" / "api.py"
    client = ROOT / "app" / "core" / "api" / "api.service.ts"
    if not backend.exists() or not client.exists():
        # Returning quietly here is how this check spent its first run doing
        # nothing: the backend path was wrong and nobody noticed.
        return [f"contract check could not run: {backend} or {client} not found"]

    tree = ast.parse(backend.read_text())
    source = client.read_text()
    problems: list[str] = []

    for ts_name, py_name in CONTRACTS.items():
        node = next(
            (n for n in ast.walk(tree) if isinstance(n, ast.ClassDef) and n.name == py_name),
            None,
        )
        match = re.search(rf"export interface {ts_name} \{{(.*?)\n\}}", source, re.S)
        if node is None or match is None:
            problems.append(f"cannot compare {ts_name} with {py_name}")
            continue

        backend_fields = {
            item.target.id for item in node.body if isinstance(item, ast.AnnAssign)
        }
        client_fields = set(re.findall(r"^\s*(\w+)\??:", match.group(1), re.M))

        for field in sorted(backend_fields - client_fields):
            problems.append(f"{ts_name}: missing '{field}' (present on {py_name})")
        for field in sorted(client_fields - backend_fields):
            problems.append(f"{ts_name}: '{field}' is not accepted by {py_name}")

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
    problems = check_decorator_literals() + check_imports() + check_request_contracts()

    if problems:
        print(f"✗ {len(problems)} problem(s) across {len(files)} TypeScript files:\n")
        for problem in problems:
            print(f"  {problem}")
        return 1

    print(
        f"✓ {len(files)} TypeScript files: decorator literals, imports and "
        "request contracts are sound"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
