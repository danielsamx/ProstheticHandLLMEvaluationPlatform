"""Persisted enumerations (stored as VARCHAR for forward compatibility)."""

from __future__ import annotations

from enum import Enum


class UserRole(str, Enum):
    ADMIN = "admin"
    RESEARCHER = "researcher"
    VIEWER = "viewer"


class ExecutionStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"        # LLM answered AND validation passed
    VALIDATION_FAILED = "validation_failed"
    PROVIDER_ERROR = "provider_error"
    TIMEOUT = "timeout"
    CANCELLED = "cancelled"


class ExperimentStatus(str, Enum):
    DRAFT = "draft"
    RUNNING = "running"
    COMPLETED = "completed"
    ARCHIVED = "archived"


class ErrorCategory(str, Enum):
    PROVIDER = "provider"          # network, auth, rate limit, model unavailable
    PARSE = "parse"                # response was not JSON
    SCHEMA = "schema"              # JSON did not match the contract
    PROTOCOL = "protocol"          # malformed serial frame
    RANGE = "range"                # position outside mechanical limits
    KINEMATIC = "kinematic"        # unreachable pose
    SAFETY = "safety"              # violated a safety rule
    INTERNAL = "internal"          # platform bug
