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


# ── Error surfacing ─────────────────────────────────────────────────────────


def test_every_unhandled_exception_has_a_handler() -> None:
    """Without a catch-all, an exception propagates through BaseHTTPMiddleware
    and can reach the browser as a reset socket rather than a response. The
    client then sees status 0, which is indistinguishable from "the server is
    down" — and the real cause stays invisible."""
    import ast
    import pathlib

    source = pathlib.Path(__file__).resolve().parent.parent / "app" / "main.py"
    tree = ast.parse(source.read_text())

    handled = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.AsyncFunctionDef):
            continue
        for decorator in node.decorator_list:
            if isinstance(decorator, ast.Call) and getattr(
                decorator.func, "attr", ""
            ) == "exception_handler":
                for arg in decorator.args:
                    if isinstance(arg, ast.Name):
                        handled.add(arg.id)

    assert "Exception" in handled, "no catch-all exception handler"
    assert "ValueError" in handled
    assert "RequestValidationError" in handled


def test_error_responses_carry_cors_headers() -> None:
    """Exception handlers run outside CORSMiddleware, so an error response would
    otherwise arrive without CORS headers and the browser would report a network
    failure instead of showing the message."""
    import pathlib

    source = (pathlib.Path(__file__).resolve().parent.parent / "app" / "main.py").read_text()
    assert "Access-Control-Allow-Origin" in source


def test_schema_check_runs_at_startup() -> None:
    import pathlib

    source = (pathlib.Path(__file__).resolve().parent.parent / "app" / "main.py").read_text()
    assert "check_and_log" in source
    assert "schema_report" in source


def test_schema_report_names_the_remedy() -> None:
    from app.core.schema_check import SchemaReport

    report = SchemaReport(ok=False, missing_columns={"executions": ["temperature"]})
    summary = report.summary()
    assert "executions" in summary and "temperature" in summary
    assert "behind" in summary.lower()


def test_healthy_schema_reports_ok() -> None:
    from app.core.schema_check import SchemaReport

    assert "matches" in SchemaReport(ok=True).summary()


# ── Structured logging ──────────────────────────────────────────────────────


def test_no_log_call_passes_a_reserved_logrecord_attribute() -> None:
    """`logging` raises on a colliding `extra` key rather than ignoring it, so a
    line written to *report* a problem takes the process down instead.

    `extra={"name": ...}` crashed the seed into a restart loop. The logger now
    renames collisions, but the call sites should not rely on that.
    """
    import ast
    import logging
    import pathlib

    probe = logging.LogRecord("l", 20, "p", 1, "m", None, None)
    reserved = set(vars(probe)) | {"message", "asctime", "taskName"}

    offenders: list[str] = []
    root = pathlib.Path(__file__).resolve().parent.parent / "app"
    for path in sorted(root.rglob("*.py")):
        for node in ast.walk(ast.parse(path.read_text())):
            if not isinstance(node, ast.Call):
                continue
            for keyword in node.keywords:
                if keyword.arg != "extra" or not isinstance(keyword.value, ast.Dict):
                    continue
                for key in keyword.value.keys:
                    if isinstance(key, ast.Constant) and key.value in reserved:
                        offenders.append(
                            f"{path.name}:{node.lineno} extra={{'{key.value}': ...}}"
                        )

    assert not offenders, "reserved LogRecord attributes in extra: " + "; ".join(offenders)


def test_the_logger_survives_a_reserved_key_anyway() -> None:
    """Belt and braces: a future call site should degrade, not crash."""
    import io
    import json
    import logging

    from app.core.logging import JsonFormatter, get_logger

    buffer = io.StringIO()
    handler = logging.StreamHandler(buffer)
    handler.setFormatter(JsonFormatter())

    root = logging.getLogger()
    previous, previous_level = root.handlers, root.level
    root.handlers, root.level = [handler], logging.INFO
    try:
        get_logger("probe").warning("collides", extra={"name": "x", "module": "y"})
    finally:
        root.handlers, root.level = previous, previous_level

    payload = json.loads(buffer.getvalue())
    # Renamed, not dropped: the value is usually the point of the line.
    assert payload["name_"] == "x"
    assert payload["module_"] == "y"


def test_every_module_compiles_not_merely_parses() -> None:
    """`ast.parse` is not enough, and this suite learned that the hard way.

    A duplicated keyword argument — `check(emg_context=x, ..., emg_context=x)` —
    parses cleanly and is rejected only by the compiler. So the whole suite went
    green while `app/api/v1/prompts.py` could not be imported at all, and the
    failure surfaced as a container restart loop instead of a test.

    `compile()` runs the same checks the interpreter does at import time,
    without executing anything or needing the optional dependencies that make
    several of these modules unimportable in a bare environment. It closes the
    gap between "the file is syntactically shaped like Python" and "the
    interpreter will accept this file".
    """
    problems: list[str] = []
    for path in sorted(BACKEND.rglob("*.py")):
        if SKIP & set(path.relative_to(BACKEND).parts):
            continue
        try:
            compile(path.read_text(), str(path), "exec")
        except SyntaxError as exc:
            problems.append(f"{path.relative_to(BACKEND)}:{exc.lineno}: {exc.msg}")

    assert not problems, "Modules the interpreter would reject:\n  " + "\n  ".join(problems)


def test_the_alembic_revisions_compile_too() -> None:
    """Excluded from the import check above, but they run on every container
    start — before the application does. A broken migration is a boot failure
    with no application log to explain it."""
    problems: list[str] = []
    for path in sorted((BACKEND / "alembic").rglob("*.py")):
        try:
            compile(path.read_text(), str(path), "exec")
        except SyntaxError as exc:
            problems.append(f"{path.name}:{exc.lineno}: {exc.msg}")

    assert not problems, "\n  ".join(problems)


def test_the_compose_command_is_a_shell_script_that_actually_runs() -> None:
    """Guards a boot failure that no Python test could have caught.

    YAML's `>` folds newlines only between lines at the block's own indentation;
    a *more* indented line keeps its newline. So splitting the uvicorn
    invocation across two lines handed `sh` a fourth line beginning with
    `--reload`, which it read as a command name — "sh: 4: --reload: not found",
    and a container that restarted forever.

    Every line but the last must therefore end in a shell continuation.
    """
    import yaml

    compose = yaml.safe_load((BACKEND.parent / "docker-compose.yml").read_text())
    for name, service in compose["services"].items():
        command = service.get("command")
        if not isinstance(command, str):
            continue
        lines = [line.rstrip() for line in command.strip().splitlines()]
        dangling = [
            f"{name} line {index}: {line.strip()!r}"
            for index, line in enumerate(lines[:-1], 1)
            if not line.endswith(("&&", "||", "\\", "|", ";"))
        ]
        assert not dangling, (
            "Shell lines that sh will read as separate commands:\n  "
            + "\n  ".join(dangling)
        )
