"""Static import audit.

A renamed constant with one stale importer is not caught by any unit test — it
surfaces at container start, as an ImportError inside uvicorn's worker. This
walks every internal `from app.x import y` and checks the name actually exists,
without needing fastapi, asyncpg or a database.
"""

from __future__ import annotations

import ast
import pathlib

BACKEND = pathlib.Path(__file__).resolve().parent.parent
SKIP = {"alembic", "__pycache__", ".venv"}


def _modules() -> dict[str, pathlib.Path]:
    found: dict[str, pathlib.Path] = {}
    for path in BACKEND.rglob("*.py"):
        if SKIP & set(path.relative_to(BACKEND).parts):
            continue
        parts = list(path.relative_to(BACKEND).with_suffix("").parts)
        if parts[-1] == "__init__":
            parts = parts[:-1]
        if parts:
            found[".".join(parts)] = path
    return found


def _top_level_names(path: pathlib.Path) -> set[str]:
    names: set[str] = set()
    tree = ast.parse(path.read_text())
    for node in tree.body:
        if isinstance(node, ast.Assign):
            names |= {t.id for t in node.targets if isinstance(t, ast.Name)}
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            names.add(node.target.id)
        elif isinstance(node, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            names.add(node.name)
        elif isinstance(node, (ast.Import, ast.ImportFrom)):
            names |= {a.asname or a.name.split(".")[0] for a in node.names}
    return names


def test_every_internal_import_resolves() -> None:
    modules = _modules()
    exports = {name: _top_level_names(path) for name, path in modules.items()}

    # A package also exposes each of its submodules by name.
    for name in list(modules):
        if "." in name:
            parent, child = name.rsplit(".", 1)
            exports.setdefault(parent, set()).add(child)

    problems: list[str] = []
    for module, path in modules.items():
        for node in ast.walk(ast.parse(path.read_text())):
            if not (isinstance(node, ast.ImportFrom) and node.module):
                continue
            if not node.module.startswith("app."):
                continue
            available = exports.get(node.module)
            if available is None:
                problems.append(f"{module}: unknown module {node.module}")
                continue
            for alias in node.names:
                if alias.name != "*" and alias.name not in available:
                    problems.append(
                        f"{module}: {node.module} has no name {alias.name!r}"
                    )

    assert not problems, "Broken internal imports:\n  " + "\n  ".join(problems)


def test_every_module_parses() -> None:
    broken = []
    for module, path in _modules().items():
        try:
            ast.parse(path.read_text())
        except SyntaxError as exc:
            broken.append(f"{module}: {exc}")
    assert not broken, "Syntax errors:\n  " + "\n  ".join(broken)
