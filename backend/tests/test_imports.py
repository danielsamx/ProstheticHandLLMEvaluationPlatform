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


# ── Local runtime addressing ────────────────────────────────────────────────


def test_loopback_is_redirected_to_the_docker_host(monkeypatch) -> None:
    """Inside a container, localhost is the container — not the developer's
    machine where LM Studio is listening."""
    import app.core.config as config

    monkeypatch.setattr(config, "running_in_container", lambda: True)

    assert config.redirect_loopback_to_host("http://localhost:1234/v1") == (
        "http://host.docker.internal:1234/v1"
    )
    assert config.redirect_loopback_to_host("http://127.0.0.1:11434") == (
        "http://host.docker.internal:11434"
    )


def test_non_loopback_addresses_are_left_alone(monkeypatch) -> None:
    import app.core.config as config

    monkeypatch.setattr(config, "running_in_container", lambda: True)

    for url in (
        "https://api.openai.com/v1",
        "http://192.168.1.50:1234/v1",
        "http://host.docker.internal:1234/v1",
    ):
        assert config.redirect_loopback_to_host(url) == url


def test_nothing_is_rewritten_outside_a_container(monkeypatch) -> None:
    """Running the backend natively, localhost is exactly right."""
    import app.core.config as config

    monkeypatch.setattr(config, "running_in_container", lambda: False)
    assert config.redirect_loopback_to_host("http://localhost:1234/v1") == (
        "http://localhost:1234/v1"
    )


def test_env_example_ships_no_active_local_runtime_override() -> None:
    """Compose interpolates .env when resolving ${VAR:-default}, so an active
    value here overrides docker-compose.yml. That is what made LM Studio
    unreachable, so the template must ship the lines commented out."""
    import pathlib

    root = pathlib.Path(__file__).resolve().parent.parent.parent
    text = (root / ".env.example").read_text()

    for line in text.splitlines():
        stripped = line.strip()
        assert not stripped.startswith("LM_STUDIO_API_BASE="), line
        assert not stripped.startswith("OLLAMA_API_BASE="), line


# ── CORS ────────────────────────────────────────────────────────────────────


def test_development_cors_accepts_every_local_origin() -> None:
    """A browser treats localhost, 127.0.0.1 and the LAN address as distinct
    origins. An exact-match list turns a harmless URL choice into every request
    failing at status 0, which reports nothing useful."""
    import re

    from app.core.config import Settings

    settings = Settings(_env_file=None, app_env="development")
    pattern = settings.cors_origin_regex
    assert pattern is not None

    for origin in (
        "http://localhost:4200",
        "http://127.0.0.1:4200",
        "http://[::1]:4200",
        "http://172.18.0.4:4200",
        "http://192.168.1.20:4200",
        "http://10.0.0.5:4200",
    ):
        assert re.match(pattern, origin), origin


def test_development_cors_still_refuses_the_public_internet() -> None:
    import re

    from app.core.config import Settings

    pattern = Settings(_env_file=None, app_env="development").cors_origin_regex
    assert pattern is not None

    for origin in ("https://evil.example.com", "http://8.8.8.8:4200", "http://172.15.0.1"):
        assert not re.match(pattern, origin), origin


def test_production_uses_the_explicit_list_only() -> None:
    from app.core.config import Settings

    assert Settings(_env_file=None, app_env="production").cors_origin_regex is None
