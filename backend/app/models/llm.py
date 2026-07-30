"""LLM providers, models and reusable sampling configurations."""

from __future__ import annotations

import uuid

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Float,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDMixin


class LlmProvider(UUIDMixin, TimestampMixin, Base):
    """A LiteLLM-routable provider.

    ``litellm_prefix`` is what LiteLLM prepends to the model key, e.g.
    ``lm_studio`` -> ``lm_studio/qwen2.5-7b-instruct``.
    """

    __tablename__ = "llm_providers"

    slug: Mapped[str] = mapped_column(String(64), unique=True, index=True, nullable=False)
    display_name: Mapped[str] = mapped_column(String(128), nullable=False)
    litellm_prefix: Mapped[str] = mapped_column(String(64), nullable=False)
    api_base: Mapped[str | None] = mapped_column(String(512))
    api_key_env_var: Mapped[str | None] = mapped_column(String(128))
    requires_api_key: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    #: Runs on the researcher's own machine (LM Studio, Ollama, vLLM).  Local
    #: providers report zero monetary cost and are exempt from rate limiting.
    is_local: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    notes: Mapped[str | None] = mapped_column(Text)

    models = relationship(
        "LlmModel", back_populates="provider", cascade="all, delete-orphan", lazy="selectin"
    )


class LlmModel(UUIDMixin, TimestampMixin, Base):
    """A concrete model exposed by a provider."""

    __tablename__ = "llm_models"
    __table_args__ = (
        UniqueConstraint("provider_id", "model_key", name="uq_llm_models_provider_model_key"),
    )

    provider_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("llm_providers.id", ondelete="CASCADE"),
        index=True, nullable=False,
    )
    model_key: Mapped[str] = mapped_column(String(256), nullable=False)
    display_name: Mapped[str] = mapped_column(String(256), nullable=False)
    family: Mapped[str | None] = mapped_column(String(64))
    parameter_count_b: Mapped[float | None] = mapped_column(Float)
    quantisation: Mapped[str | None] = mapped_column(String(32))
    context_window: Mapped[int | None] = mapped_column(Integer)
    max_output_tokens: Mapped[int | None] = mapped_column(Integer)

    supports_json_mode: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    supports_json_schema: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    supports_seed: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    supports_top_k: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    supports_penalties: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    input_cost_per_1k: Mapped[float] = mapped_column(Numeric(12, 8), default=0, nullable=False)
    output_cost_per_1k: Mapped[float] = mapped_column(Numeric(12, 8), default=0, nullable=False)

    is_enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    metadata_json: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)

    provider = relationship("LlmProvider", back_populates="models", lazy="joined")
    configurations = relationship(
        "SamplingConfiguration", back_populates="model", cascade="all, delete-orphan"
    )

    @property
    def litellm_model(self) -> str:
        prefix = self.provider.litellm_prefix if self.provider else ""
        return f"{prefix}/{self.model_key}" if prefix else self.model_key


class SamplingConfiguration(UUIDMixin, TimestampMixin, Base):
    """A named, reusable decoding configuration.

    These are the entries behind the left panel's "reusable configuration
    history": save once, replay across models to keep comparisons honest.
    """

    __tablename__ = "sampling_configurations"
    __table_args__ = (
        CheckConstraint("temperature >= 0 AND temperature <= 2", name="temperature_range"),
        CheckConstraint("top_p > 0 AND top_p <= 1", name="top_p_range"),
        CheckConstraint("max_tokens > 0", name="max_tokens_positive"),
    )

    name: Mapped[str] = mapped_column(String(160), nullable=False, index=True)
    description: Mapped[str | None] = mapped_column(Text)
    model_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("llm_models.id", ondelete="CASCADE"),
        index=True, nullable=False,
    )
    owner_id: Mapped[uuid.UUID | None] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), index=True
    )

    temperature: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    top_p: Mapped[float] = mapped_column(Float, default=1.0, nullable=False)
    top_k: Mapped[int | None] = mapped_column(Integer)
    max_tokens: Mapped[int] = mapped_column(Integer, default=1024, nullable=False)
    seed: Mapped[int | None] = mapped_column(Integer)
    frequency_penalty: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    presence_penalty: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    stop_sequences: Mapped[list] = mapped_column(JSONB, default=list, nullable=False)
    #: "text" | "json_object" | "json_schema"
    response_format: Mapped[str] = mapped_column(String(32), default="json_object", nullable=False)
    #: Anything provider-specific LiteLLM should pass through untouched.
    extra_params: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)

    #: Suppress the model's thinking channel.
    #:
    #: On by default, and the single most consequential setting for a reasoning
    #: model on this task. Qwen3-class models split their output: the working-out
    #: goes to a reasoning channel and the answer to `content`. Given a hard
    #: classification and a small token budget, such a model can spend the whole
    #: budget deliberating and return an empty answer — or an `intent` with no
    #: command behind it.
    #:
    #: The same model, same prompt, with thinking off in LM Studio's chat,
    #: answered `{"C":250,"D":280,"E":0,"F":0}`. Through the API with thinking
    #: on it answered `{"intent":"no_action","commands":[]}`. Nothing else
    #: differed.
    #:
    #: There is nothing to reason about here anyway: the task is to read eight
    #: numbers and name a gesture. Deliberation buys no accuracy and costs the
    #: budget the answer needs.
    disable_reasoning: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    is_favorite: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    use_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    model = relationship("LlmModel", back_populates="configurations", lazy="joined")

    def to_litellm_kwargs(self) -> dict:
        """Decoding parameters in LiteLLM's vocabulary.

        ``None`` values are omitted so that runtimes which do not implement a
        knob (LM Studio ignores ``top_k`` for some engines) are not sent it.
        """
        kwargs: dict = {
            "temperature": self.temperature,
            "top_p": self.top_p,
            "max_tokens": self.max_tokens,
            "frequency_penalty": self.frequency_penalty,
            "presence_penalty": self.presence_penalty,
        }
        if self.top_k is not None:
            kwargs["top_k"] = self.top_k
        if self.seed is not None:
            kwargs["seed"] = self.seed
        if self.stop_sequences:
            kwargs["stop"] = self.stop_sequences

        if self.disable_reasoning:
            # Two mechanisms, because no single one works everywhere.
            #
            # `chat_template_kwargs.enable_thinking` is the Qwen3 convention and
            # is read by the chat template itself, which is what LM Studio
            # applies. `reasoning_effort` is the OpenAI spelling that newer
            # runtimes honour. Sending both covers the models this platform
            # actually targets; a runtime that understands neither ignores them,
            # which is the same behaviour as not asking.
            kwargs["chat_template_kwargs"] = {"enable_thinking": False}
            kwargs["reasoning_effort"] = "none"

        kwargs.update(self.extra_params or {})
        return kwargs
