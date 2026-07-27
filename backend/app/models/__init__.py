"""SQLAlchemy models. Importing this package registers every mapper."""

from app.models.emg import EmgStreamSession, EmgWindowRecord  # noqa: F401
from app.models.enums import (  # noqa: F401
    ErrorCategory,
    ExecutionStatus,
    ExperimentStatus,
    UserRole,
)
from app.models.experiment import Execution, Experiment  # noqa: F401
from app.models.llm import LlmModel, LlmProvider, SamplingConfiguration  # noqa: F401
from app.models.metrics import ExecutionMetric, SimulatorMovement  # noqa: F401
from app.models.prompts import (  # noqa: F401
    DynamicPromptTemplate,
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
    "User", "LlmProvider", "LlmModel", "SamplingConfiguration",
    "SystemPromptVersion", "TechnicalContextVersion", "DynamicPromptTemplate",
    "LabPreset", "EmgWindowRecord", "EmgStreamSession", "Experiment",
    "Execution", "ValidationResult", "ValidationIssueRecord", "ExecutionError",
    "ExecutionMetric", "SimulatorMovement", "UserRole", "ExecutionStatus",
    "ExperimentStatus", "ErrorCategory",
]
