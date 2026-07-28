"""Auditing, traceability and export.

These cover the platform's central promise — that any recorded run can be
reconstructed and audited — and the places where that promise is easiest to
break silently.
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone

import pytest

from app.core.request_context import (
    RequestContext,
    build_context,
    parse_browser,
    parse_device_type,
    parse_operating_system,
)
from app.models.audit import AuditAction, AuditOutcome
from app.schemas.governance import ExportRequest, ProjectIn
from app.services import audit_service, export_service
from app.services.traceability_service import REPRODUCIBILITY_REQUIREMENTS


# ── Request context ─────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "agent,browser,os_name,device",
    [
        ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/131.0 Safari/537.36",
         "Chrome", "Windows 10/11", "desktop"),
        ("Mozilla/5.0 (Windows NT 10.0) Chrome/131.0 Safari/537.36 Edg/131.0",
         "Edge", "Windows 10/11", "desktop"),
        ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) Version/17.0 Safari/605.1.15",
         "Safari", "macOS", "desktop"),
        ("Mozilla/5.0 (iPad; CPU OS 17_0 like Mac OS X) Safari/604.1",
         "Safari", "iPadOS", "tablet"),
        ("Mozilla/5.0 (Linux; Android 14) Chrome/131.0 Mobile Safari/537.36",
         "Chrome", "Android", "mobile"),
    ],
)
def test_user_agent_is_parsed_into_browser_os_and_device(agent, browser, os_name, device):
    assert parse_browser(agent) == browser
    assert parse_operating_system(agent) == os_name
    assert parse_device_type(agent) == device


def test_edge_is_not_reported_as_chrome():
    """Edge's user agent contains 'Chrome/', so order of testing matters."""
    agent = "Mozilla/5.0 (Windows NT 10.0) Chrome/131.0 Safari/537.36 Edg/131.0"
    assert parse_browser(agent) == "Edge"


def test_context_carries_a_request_id_even_when_none_supplied():
    context = build_context(
        client_ip="10.0.0.1", user_agent=None, session_id=None, request_id=None
    )
    assert uuid.UUID(context.request_id)


def test_origin_payload_contains_every_provenance_field():
    context = build_context(
        client_ip="10.0.0.1",
        user_agent="Mozilla/5.0 (Windows NT 10.0) Chrome/131.0 Safari/537.36",
        session_id="sess-1",
        request_id="req-1",
    )
    origin = context.as_origin()
    assert set(origin) == {
        "client_ip", "user_agent", "browser", "operating_system",
        "device_type", "session_id", "request_id",
    }
    assert origin["browser"] == "Chrome"


# ── Audit diffing ───────────────────────────────────────────────────────────


def test_diff_records_only_what_changed():
    changes = audit_service.diff(
        {"name": "old", "status": "active", "tags": []},
        {"name": "new", "status": "active", "tags": []},
    )
    assert changes == {"name": {"from": "old", "to": "new"}}


def test_diff_ignores_timestamps():
    """They change on every write and would drown the actual edit."""
    before = {"name": "a", "updated_at": datetime(2026, 1, 1, tzinfo=timezone.utc)}
    after = {"name": "a", "updated_at": datetime(2026, 6, 1, tzinfo=timezone.utc)}
    assert audit_service.diff(before, after) == {}


def test_diff_redacts_secrets():
    changes = audit_service.diff({"api_key": "sk-old"}, {"api_key": "sk-new"})
    assert changes["api_key"] == {"from": "[redacted]", "to": "[redacted]"}


@pytest.mark.parametrize("field", ["password", "hashed_password", "api_key", "secret", "token"])
def test_every_sensitive_field_name_is_redacted(field):
    changes = audit_service.diff({field: "before"}, {field: "after"})
    assert changes[field]["to"] == "[redacted]"


def test_long_values_are_summarised_not_duplicated():
    """The full text already lives in its own versioned row."""
    long_text = "x" * 5000
    changes = audit_service.diff({"content": "short"}, {"content": long_text})
    assert "5000 chars" in changes["content"]["to"]
    assert len(changes["content"]["to"]) < 600


def test_creation_diff_treats_absent_before_as_empty():
    changes = audit_service.diff(None, {"name": "new project"})
    assert changes["name"] == {"from": None, "to": "new project"}


# ── Action catalogue ────────────────────────────────────────────────────────


def test_audit_actions_cover_every_required_event():
    """The brief names these explicitly; a missing one is an untracked event."""
    required = {
        "project.created", "project.updated", "project.deleted",
        "prompt.created", "prompt.edited", "execution.completed",
        "model.selected", "config.updated", "export.requested",
        "auth.login", "auth.logout",
    }
    assert required <= {action.value for action in AuditAction}


def test_action_values_are_namespaced():
    """`group.verb` keeps the catalogue aggregatable by area."""
    for action in AuditAction:
        assert "." in action.value, action


def test_outcomes_distinguish_failure_from_denial():
    assert {o.value for o in AuditOutcome} == {"success", "failure", "denied"}


# ── Traceability ────────────────────────────────────────────────────────────


def test_reproducibility_requirements_cover_the_stated_questions():
    """Prompt, model, parameters, stimulus — the questions the brief asks a
    past execution to answer."""
    attributes = {attribute for attribute, _ in REPRODUCIBILITY_REQUIREMENTS}
    assert {"system_prompt_text", "technical_context_text", "dynamic_prompt_text"} <= attributes
    assert "litellm_model" in attributes
    assert "model_snapshot" in attributes
    assert "emg_window_id" in attributes


# ── Export ──────────────────────────────────────────────────────────────────


def test_export_columns_cover_condition_outcome_and_cost():
    columns = set(export_service.BASE_COLUMNS)
    # Independent variables
    assert {"litellm_model", "temperature", "top_p", "seed", "limit_profile"} <= columns
    # Dependent variables
    assert {"validation_passed", "gesture_correct", "latency_ms", "total_tokens"} <= columns
    # Comparability key
    assert "frozen_context_sha256" in columns
    # Provenance
    assert {"triggered_by_email", "session_id"} <= columns


def test_empty_export_still_emits_the_header():
    """A downstream reader must get a parseable file, not zero bytes."""
    csv_text = export_service.to_csv([])
    assert csv_text.splitlines()[0].split(",")[0] == "execution_id"


def test_booleans_are_written_lowercase_for_pandas_and_r():
    csv_text = export_service.to_csv([{"execution_id": "x", "validation_passed": True}])
    assert ",true" in csv_text or csv_text.strip().endswith("true")
    assert "True" not in csv_text


def test_nested_values_are_json_encoded_in_csv():
    csv_text = export_service.to_csv([{"execution_id": "x", "stop_sequences": ["a", "b"]}])
    assert '["a", "b"]' in csv_text or '""a"", ""b""' in csv_text


def test_jsonl_rows_are_individually_parseable():
    rows = [{"execution_id": "a", "cost_usd": 0.1}, {"execution_id": "b", "cost_usd": 0.2}]
    lines = list(export_service.to_jsonl(rows))
    assert len(lines) == 2
    assert json.loads(lines[0])["execution_id"] == "a"


def test_jsonl_serialises_uuid_and_datetime():
    line = next(export_service.to_jsonl([
        {"id": uuid.uuid4(), "at": datetime.now(timezone.utc)}
    ]))
    payload = json.loads(line)
    assert isinstance(payload["id"], str)
    assert isinstance(payload["at"], str)


def test_failures_are_included_by_default():
    """Excluding them silently biases any success rate computed downstream."""
    assert ExportRequest().only_validated is False


def test_heavy_columns_are_opt_in():
    """Prompts multiply file size roughly thirtyfold; the matrix far more."""
    request = ExportRequest()
    assert request.include_prompts is False
    assert request.include_raw_response is False
    assert request.include_emg_matrix is False


# ── Projects ────────────────────────────────────────────────────────────────


def test_project_slug_is_normalised():
    assert ProjectIn(name="Study", slug="  My Study  ").slug == "my-study"


def test_project_slug_rejects_punctuation():
    with pytest.raises(ValueError):
        ProjectIn(name="Study", slug="my/study")


def test_project_slug_is_optional():
    assert ProjectIn(name="Grasp comparison").slug is None


# ── Model catalogue honesty ─────────────────────────────────────────────────


def _seed_source() -> str:
    """Read the seed as text.

    Importing it would open a database engine, which the suite deliberately does
    not require — these checks are about what the seed *declares*, not what it
    does at runtime.
    """
    import pathlib as _p

    return (_p.Path(__file__).resolve().parent.parent / "app" / "seeds" / "seed.py").read_text()


def test_seed_ships_no_invented_local_models() -> None:
    """A dropdown offering a model the researcher never downloaded is worse than
    an empty one: it fails at inference with a provider error that looks like a
    connectivity problem. What is installed is knowable, so guessing is both
    unnecessary and misleading."""
    import ast

    tree = ast.parse(_seed_source())
    models = next(
        node for node in tree.body
        if isinstance(node, ast.AnnAssign)
        and getattr(node.target, "id", "") == "MODELS"
    )
    assert ast.literal_eval(models.value) == []


def test_placeholder_cleanup_preserves_referenced_models() -> None:
    """Traceability: a past result must still resolve to the model it ran
    against, so a referenced row is never deleted."""
    source = _seed_source()

    assert "_remove_unused_placeholders" in source
    assert "Execution.llm_model_id == model.id" in source
    assert "placeholder_kept" in source, "referenced placeholders must be kept"


def test_availability_is_distinct_from_enabled() -> None:
    """`is_available` answers 'can this run now', which is a different question
    from whether the catalogue entry is enabled — and both differ from 'the
    runtime was unreachable', which must stay unknown rather than false."""
    from app.schemas.api import ModelOut

    assert "is_available" in ModelOut.model_fields
    assert ModelOut.model_fields["is_available"].default is None


def test_only_lm_studio_ships_enabled() -> None:
    """An unselectable provider in a dropdown is clutter; a provider with no API
    key configured is worse, because it fails at inference time. The other rows
    are retained so enabling one is a flag flip rather than a migration."""
    import re

    source = _seed_source()
    block = source[source.index("PROVIDERS = ["):source.index("#: The catalogue ships EMPTY")]

    enabled: dict[str, bool] = {}
    for slug in re.findall(r'"slug": "(\w+)"', block):
        entry = block[block.index(f'"slug": "{slug}"'):]
        entry = entry[: entry.index("},")]
        enabled[slug] = '"is_enabled": False' not in entry

    assert enabled == {
        "lm_studio": True,
        "ollama": False,
        "openai": False,
        "anthropic": False,
    }


def test_provider_enablement_self_heals_on_reseed() -> None:
    """An existing database keeps its old rows; the seed must correct them
    rather than only apply to a fresh install."""
    source = _seed_source()
    assert "updated_provider_enabled" in source
    assert "row.is_enabled = desired" in source


def test_importing_a_model_also_creates_a_way_to_run_it() -> None:
    """A catalogue entry with no sampling configuration cannot be executed, and
    the Run button is disabled with nothing on screen to explain it.

    This was the gap left by emptying the seeded model list: the seed created
    configurations only for seeded models, and the import created none at all.
    """
    import pathlib

    source = (
        pathlib.Path(__file__).resolve().parent.parent
        / "app" / "api" / "v1" / "providers.py"
    ).read_text()

    assert "SamplingConfiguration(" in source, "import creates no configuration"
    assert "temperature=0.0" in source, "the baseline must be the control condition"
    assert "seed=42" in source


def test_the_seed_backfills_models_left_without_a_configuration() -> None:
    """Existing installs imported models before the import created one."""
    source = _seed_source()
    assert "_backfill_missing_configurations" in source
    assert "backfilled_configuration" in source
