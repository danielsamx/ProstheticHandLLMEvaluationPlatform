"""The documentation, checked against the code it describes.

Documentation rots silently. Nothing fails when a README keeps describing a
parameter that was deleted a month ago — it just quietly misleads whoever reads
it next, and the person most likely to be misled is the author, a year later,
trying to remember how their own platform works.

These tests pin the parts of the prose that are *checkable facts*: route paths,
table names, migration revisions, prompt block versions. They deliberately do not
touch the reasoning, which is the majority of the text and cannot be verified
mechanically.

Everything is read from source rather than imported, because the test suite runs
where FastAPI and SQLAlchemy may not be installed, and because a doc test that
needs the whole application to boot is a doc test that gets skipped.

Real defects this caught on its first run:

* ``/hand/output-schema`` in both API references. The route is
  ``/hand/output-contract``; a reader following the doc gets a 404.
* A whole documented request body for ``/emg/parse`` — ``normalisation``,
  ``full_scale`` — describing a normalisation step that was removed when the
  platform moved to raw EMG. The schema now forbids unknown fields, so the
  documented example returns 422.
* Both references describing three prompt blocks after the fourth was added.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
API_DIR = ROOT / "backend" / "app" / "api" / "v1"
MODELS_DIR = ROOT / "backend" / "app" / "models"
MIGRATIONS_DIR = ROOT / "backend" / "alembic" / "versions"
DOCS = [
    ROOT / "README.md",
    ROOT / "docs" / "README.md",
    *sorted((ROOT / "docs" / "en").glob("*.md")),
    *sorted((ROOT / "docs" / "es").glob("*.md")),
]

#: Paths named in prose that are not routes of this API.
#:
#: Three different things wear the same shape in prose. WebSocket channels are
#: mounted outside the versioned router; `/logs` and `/lab` are Angular routes in
#: the browser; `/v1/models` belongs to LM Studio. Documenting them is correct —
#: asserting that FastAPI serves them is not.
_NOT_OUR_ROUTES = {
    "/docs",
    "/redoc",
    "/health",
    "/",
    "/v1/models",  # LM Studio's own endpoint
    "/lab",
    "/logs",
    "/dashboard",
}

#: Prefixes of paths that are documented but are not versioned API routes.
_NOT_OUR_PREFIXES = ("/ws/",)


def _route_table() -> set[str]:
    """Every path this API serves, as `/prefix/suffix`.

    Read with :mod:`ast` rather than by importing the app: the decorators are
    what carry the paths, and they are visible in the syntax tree without
    FastAPI being installed.
    """
    routes: set[str] = set()

    for path in sorted(API_DIR.glob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        prefixes: dict[str, str] = {}

        # `router = APIRouter(prefix="/movement", ...)` — one module may define
        # several routers, and they do not share a prefix.
        for node in ast.walk(tree):
            if not isinstance(node, ast.Assign) or not isinstance(node.value, ast.Call):
                continue
            func = node.value.func
            if getattr(func, "id", getattr(func, "attr", None)) != "APIRouter":
                continue
            prefix = next(
                (
                    kw.value.value
                    for kw in node.value.keywords
                    if kw.arg == "prefix" and isinstance(kw.value, ast.Constant)
                ),
                "",
            )
            for target in node.targets:
                if isinstance(target, ast.Name):
                    prefixes[target.id] = prefix

        for node in ast.walk(tree):
            if not isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
                continue
            for decorator in node.decorator_list:
                if not isinstance(decorator, ast.Call):
                    continue
                attribute = decorator.func
                if not isinstance(attribute, ast.Attribute):
                    continue
                owner = getattr(attribute.value, "id", None)
                if owner not in prefixes:
                    continue
                if attribute.attr not in {"get", "post", "put", "patch", "delete"}:
                    continue
                if not decorator.args or not isinstance(decorator.args[0], ast.Constant):
                    continue
                routes.add(prefixes[owner] + decorator.args[0].value)

    return routes


def _generalise(path: str) -> str:
    """`/executions/{id}/prompt` and `/executions/{execution_id}/prompt` are one route.

    Documentation names a parameter for the reader; code names it for the
    handler. Requiring them to match would be pedantry that makes the test
    annoying rather than useful.
    """
    return re.sub(r"\{[^}]*\}", "{}", path.rstrip("/"))


def _documented_paths() -> dict[str, list[Path]]:
    """Every API path a document claims exists, and where it says so."""
    found: dict[str, list[Path]] = {}
    pattern = re.compile(r"`(/(?:api/v1)?[a-z0-9\-{}/_.]*)`", re.IGNORECASE)

    for doc in DOCS:
        for match in pattern.findall(doc.read_text(encoding="utf-8")):
            path = match.removeprefix("/api/v1")
            if not path or path in _NOT_OUR_ROUTES or "." in path:
                continue
            if path.startswith(_NOT_OUR_PREFIXES):
                continue
            found.setdefault(path, []).append(doc)

    return found


def test_every_documented_route_exists() -> None:
    """A path in the docs must be a path in the code.

    The failure this exists for is the quiet kind: a route gets renamed, the
    handler and its tests move with it, and only the documentation is left
    pointing at a 404.
    """
    real = {_generalise(route) for route in _route_table()}
    assert real, "No routes were parsed - the extractor is broken, not the docs."

    broken = {
        path: [doc.name for doc in docs]
        for path, docs in _documented_paths().items()
        if _generalise(path) not in real
    }

    assert not broken, "Documented routes that do not exist:\n" + "\n".join(
        f"  {path}  (in {', '.join(sorted(set(docs)))})" for path, docs in sorted(broken.items())
    )


def test_every_documented_table_exists() -> None:
    """Table names in the database reference must be real tables."""
    declared = set(
        re.findall(
            r'__tablename__\s*=\s*"([a-z_]+)"',
            "\n".join(p.read_text(encoding="utf-8") for p in MODELS_DIR.glob("*.py")),
        )
    )
    assert declared, "No tables were parsed."

    for doc in (ROOT / "docs" / "en" / "database.md", ROOT / "docs" / "es" / "base-de-datos.md"):
        headings = re.findall(r"^#### `([a-z_]+)`", doc.read_text(encoding="utf-8"), re.MULTILINE)
        unknown = [name for name in headings if name not in declared]
        assert not unknown, f"{doc.name} documents tables that do not exist: {unknown}"


def test_the_documented_tables_cover_the_new_ones() -> None:
    """The reverse direction: a new table must reach the documentation.

    Weaker than the forward check by design — not every table needs its own
    heading — but the two added most recently carry behaviour a reader cannot
    guess, so they are named explicitly.
    """
    for doc in (ROOT / "docs" / "en" / "database.md", ROOT / "docs" / "es" / "base-de-datos.md"):
        text = doc.read_text(encoding="utf-8")
        for table in ("movement_log", "prompt_configurations", "emg_context_versions"):
            assert table in text, f"{doc.name} never mentions `{table}`."


def test_every_documented_migration_exists() -> None:
    """A migration table that lists revisions must list real ones."""
    revisions = {path.stem for path in MIGRATIONS_DIR.glob("*.py")}
    assert revisions, "No migrations were found."

    for doc in (ROOT / "docs" / "en" / "database.md", ROOT / "docs" / "es" / "base-de-datos.md"):
        text = doc.read_text(encoding="utf-8")
        documented = set(re.findall(r"`(0\d{3}_[a-z_]+)`", text))
        unknown = documented - revisions
        assert not unknown, f"{doc.name} documents missing migrations: {sorted(unknown)}"
        missing = revisions - documented
        assert not missing, f"{doc.name} omits migrations: {sorted(missing)}"


#: Sentences that assert the prompt *has* three blocks, as opposed to the many
#: correct sentences about the three *frozen* ones. Matching the bare phrase
#: "three blocks" fails on "the three block versions" and on every Spanish
#: mention of "los tres bloques congelados", which are all true.
_STALE_BLOCK_CLAIMS = (
    "three blocks, assembled",
    "has three blocks",
    "three blocks and deterministic",
    "returns the three blocks",
    "three versioned artefacts",
    "three-block prompt",
    "tiene tres bloques",
    "de tres bloques",
    "tres bloques y ensamblado",
    "devuelve los tres bloques",
    "tres artefactos versionados",
)


def test_no_document_still_claims_the_prompt_has_three_blocks() -> None:
    """The fourth block must have reached every document that counts them.

    It was split out of the second precisely so the two could be varied
    independently. A reader told there are three will look for the EMG guidance
    inside the hardware description, fail to find it, and conclude the platform
    does not provide any.
    """
    for doc in DOCS:
        text = doc.read_text(encoding="utf-8").lower()
        found = [claim for claim in _STALE_BLOCK_CLAIMS if claim in text]
        assert not found, f"{doc.name} still claims a three-block prompt: {found}"


def test_the_block_diagrams_show_the_fourth_block() -> None:
    """A document drawing the prompt must draw all four blocks.

    Separate from the sentence check because the diagram is what a reader
    actually looks at, and prose can be corrected while the picture beside it
    still shows three boxes.
    """
    for doc in DOCS:
        text = doc.read_text(encoding="utf-8")
        if "1 · SYSTEM PROMPT" not in text:
            continue
        # Matched on the numbering rather than the block's name, because the
        # Spanish diagrams label it "4 · PROMPT DINÁMICO". A test that only knew
        # the English wording would pass on a Spanish diagram still showing three.
        assert re.search(r"│\s*4 · ", text), (
            f"{doc.name} draws the prompt but its diagram stops at three blocks."
        )


def test_no_document_describes_the_removed_normalisation_step() -> None:
    """EMG is raw. Nothing rescales it, and no document may say otherwise.

    This one is worth a test rather than a careful read, because the removed
    parameters had plausible names. `full_scale` in a document reads like
    something that must still exist; the request schema forbids extra fields, so
    following that document produces a 422 with no clue as to why.
    """
    removed = re.compile(r"`(normalisation|full_scale|inferred_full_scale|divisor)`")

    for doc in DOCS:
        match = removed.search(doc.read_text(encoding="utf-8"))
        assert match is None, (
            f"{doc.name} documents `{match.group(1)}`, a parameter removed when the "
            "platform moved to raw EMG."
        )


def test_the_documented_prompt_versions_match_the_code() -> None:
    """Version constants quoted in prose must be the ones that ship.

    The seed keys artefacts on (name, version). A document quoting a version the
    code no longer uses sends a reader looking for a row that was never written.
    """
    source = (ROOT / "backend" / "app" / "prompts").glob("*.py")
    versions = dict(
        re.findall(
            r'(\w+_VERSION):\s*Final\[str\]\s*=\s*"([\d.]+)"',
            "\n".join(p.read_text(encoding="utf-8") for p in source),
        )
    )

    # Deliberately *not* pinned to specific numbers.
    #
    # The first version of this test asserted 1.0 / 1.1 / 1.1, and broke the
    # moment the blocks were legitimately revised — failing on a correct change
    # and saying nothing about the documentation, which is what it exists to
    # check. A test that freezes a constant is not verifying agreement between
    # two things; it is adding a third thing to keep in step.
    for name in ("SYSTEM_PROMPT_VERSION", "TECHNICAL_CONTEXT_VERSION", "EMG_CONTEXT_VERSION"):
        assert name in versions, f"{name} was renamed; the docs quote a label built from it."

    # The label format documented in both READMEs, built from those constants.
    expected_label = (
        f"S{versions['SYSTEM_PROMPT_VERSION']} · "
        f"T{versions['TECHNICAL_CONTEXT_VERSION']} · "
        f"E{versions['EMG_CONTEXT_VERSION']}"
    )
    for doc in DOCS:
        text = doc.read_text(encoding="utf-8")
        labels = re.findall(r"`(S[\d.]+ · T[\d.]+ · E[\d.]+)`", text)
        for label in labels:
            assert label == expected_label, (
                f"{doc.name} shows the configuration label `{label}`, but the shipped "
                f"blocks would render `{expected_label}`."
            )


def test_the_documented_timeout_matches_the_configuration() -> None:
    """A timeout quoted in prose must be the one that will actually apply.

    Both `.env.example` and the application default are checked, because Compose
    reads `.env` for interpolation *and* passes it into the container: a stale
    value there beats the code in both directions, which is exactly the confusion
    the documentation is trying to prevent.
    """
    config = (ROOT / "backend" / "app" / "core" / "config.py").read_text(encoding="utf-8")
    default = re.search(r"llm_request_timeout_s:\s*float\s*=\s*([\d.]+)", config)
    assert default, "The timeout setting was renamed; the docs quote a number for it."
    assert float(default.group(1)) == 1800.0

    env_example = (ROOT / ".env.example").read_text(encoding="utf-8")
    assert "LLM_REQUEST_TIMEOUT_S=1800" in env_example
