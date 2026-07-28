"""Value objects produced by the validation pipeline."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class Severity(str, Enum):
    ERROR = "error"      # blocks execution
    WARNING = "warning"  # recorded, does not block


class ValidationStage(str, Enum):
    """The gate a response must clear before it can move anything.

    Seven stages. The response carries two representations of the same
    decision — a `serial_command` string and the `intent`/`gesture`/`commands`
    structure beside it — so `schema` checks the object has the declared shape
    and `consistency` checks the two representations agree. Neither stage
    exists under a bare-command contract, because there is nothing for a lone
    command line to contradict.

    Order matters: each stage assumes its predecessors passed, and the first
    error stops the pipeline. Reporting that a position is out of range is
    meaningless if the command it came from could not be parsed.
    """

    PARSE = "parse"              # a JSON object could be recovered
    SCHEMA = "schema"            # it matches the declared response shape
    PROTOCOL = "protocol"        # serial_command is a well-formed command
    CONSISTENCY = "consistency"  # the command agrees with the structure
    RANGE = "range"              # positions inside the active limit profile
    KINEMATIC = "kinematic"      # the pose is physically reachable
    SAFETY = "safety"            # exclusivity, speed, collision rules


@dataclass(slots=True)
class ValidationIssue:
    stage: ValidationStage
    code: str
    message: str
    severity: Severity = Severity.ERROR
    field_path: str | None = None
    context: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "stage": self.stage.value,
            "code": self.code,
            "message": self.message,
            "severity": self.severity.value,
            "field_path": self.field_path,
            "context": self.context,
        }


@dataclass(slots=True)
class ValidationReport:
    """Outcome of the full pipeline for a single LLM response."""

    passed: bool = False
    stages_completed: list[ValidationStage] = field(default_factory=list)
    issues: list[ValidationIssue] = field(default_factory=list)
    limit_profile: str = ""
    parsed_command: Any | None = None      # ProstheticCommand
    resolved_pose: Any | None = None       # HandPose
    normalised_serial: str | None = None

    @property
    def errors(self) -> list[ValidationIssue]:
        return [i for i in self.issues if i.severity is Severity.ERROR]

    @property
    def warnings(self) -> list[ValidationIssue]:
        return [i for i in self.issues if i.severity is Severity.WARNING]

    @property
    def failed_stage(self) -> ValidationStage | None:
        return self.errors[0].stage if self.errors else None

    def add(self, issue: ValidationIssue) -> None:
        self.issues.append(issue)

    def to_dict(self) -> dict[str, Any]:
        return {
            "passed": self.passed,
            "limit_profile": self.limit_profile,
            "stages_completed": [s.value for s in self.stages_completed],
            "failed_stage": self.failed_stage.value if self.failed_stage else None,
            "error_count": len(self.errors),
            "warning_count": len(self.warnings),
            "issues": [i.to_dict() for i in self.issues],
            "normalised_serial": self.normalised_serial,
        }
