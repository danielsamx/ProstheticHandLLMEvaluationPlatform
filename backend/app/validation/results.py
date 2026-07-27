"""Value objects produced by the validation pipeline."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class Severity(str, Enum):
    ERROR = "error"      # blocks execution
    WARNING = "warning"  # recorded, does not block


class ValidationStage(str, Enum):
    PARSE = "parse"                # response is valid JSON
    SCHEMA = "schema"              # matches ProstheticCommand
    PROTOCOL = "protocol"          # serial_command is well formed
    CONSISTENCY = "consistency"    # serial_command agrees with structured fields
    RANGE = "range"                # positions inside the active limit profile
    KINEMATIC = "kinematic"        # pose is physically reachable
    SAFETY = "safety"              # speed, collision, force, exclusivity rules


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
