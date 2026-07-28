"""SQLAlchemy models. Importing this package registers every mapper."""

from app.models.attachment import Attachment  # noqa: F401
from app.models.audit import AuditAction, AuditLog, AuditOutcome  # noqa: F401
from app.models.emg import EmgStreamSession, EmgWindowRecord  # noqa: F401
from app.models.enums import (  # noqa: F401
    ErrorCategory,
    ExecutionStatus,
    ExperimentStatus,
    UserRole,
)
from app.models.execution_log import ExecutionLog, LogLevel  # noqa: F401
from app.models.experiment import Execution, Experiment  # noqa: F401
from app.models.llm import LlmModel, LlmProvider, SamplingConfiguration  # noqa: F401
from app.models.metrics import ExecutionMetric, SimulatorMovement  # noqa: F401
from app.models.project import Project, ProjectStatus  # noqa: F401
from app.models.prompts import (  # noqa: F401
    DynamicPromptTemplate,
    EmgContextVersion,
    LabPreset,
    SystemPromptVersion,
    TechnicalContextVersion,
)
from app.models.user import User  # noqa: F401
from app.models.validation import (  # noqa: F401
    ExecutionError,
    ValidationIssueRecord,
    ValidationResult,
)

__all__ = [
    # Identity & organisation
    "User", "UserRole", "Project", "ProjectStatus",
    # Catalogue
    "LlmProvider", "LlmModel", "SamplingConfiguration",
    # Versioned prompt artefacts
    "SystemPromptVersion", "TechnicalContextVersion", "DynamicPromptTemplate",
    "LabPreset",
    # Stimulus
    "EmgWindowRecord", "EmgStreamSession",
    # Experimentation
    "Experiment", "ExperimentStatus", "Execution", "ExecutionStatus",
    # Outcome
    "ValidationResult", "ValidationIssueRecord", "ExecutionError", "ErrorCategory",
    "ExecutionMetric", "SimulatorMovement", "ExecutionLog", "LogLevel",
    # Governance
    "AuditLog", "AuditAction", "AuditOutcome", "Attachment",
]
