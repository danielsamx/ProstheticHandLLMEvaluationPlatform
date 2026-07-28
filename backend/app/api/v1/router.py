"""Aggregated v1 router."""

from fastapi import APIRouter

from app.api.v1 import (
    configurations,
    emg,
    executions,
    experiments,
    governance,
    hand,
    projects,
    prompts,
    providers,
)

api_router = APIRouter()

# Reference data
api_router.include_router(hand.router)
api_router.include_router(providers.router)

# Organisation
api_router.include_router(projects.router)
api_router.include_router(experiments.router)

# Configuration
api_router.include_router(configurations.router)
api_router.include_router(configurations.presets_router)
api_router.include_router(prompts.router)

# Experimentation
api_router.include_router(emg.router)
api_router.include_router(executions.router)

# Governance: audit, traceability, export
api_router.include_router(governance.router)
