"""Domain layer: hardware truth extracted from the HANDi EPN V3 technical manuals.

This package is the single source of truth about the physical prosthesis.  It is
compiled from four technical manuals that were analysed during development:

  * ``Manual Handi_EPN_V3_ES.pdf``  - command glossary, ranges, gestures, protocol
  * ``Assembly Manual.pdf``         - HANDi Hand digit/joint naming, mechanics
  * ``CONEXIONES.PDF``              - electrical wiring, multiplexer/sensor map
  * ``DIAGRAMA DE BLOQUES.pdf``     - system block diagram

The PDFs are NOT read at runtime.  No RAG, no embeddings, no vector store.
Everything the LLM needs is baked into code, validators and prompt templates.
"""

from app.domain.hand_spec import (  # noqa: F401
    ACTUATORS,
    GESTURES,
    LIMIT_PROFILES,
    Actuator,
    ActuatorSpec,
    ControlCommand,
    Digit,
    GestureSpec,
    Handedness,
    Joint,
    JointType,
    LimitProfile,
    LimitProfileId,
    get_limit_profile,
)
