"""Aggregated v1 router."""

from fastapi import APIRouter

from app.api.v1 import configurations, emg, executions, experiments, hand, prompts, providers

api_router = APIRouter()
api_router.include_router(hand.router)
api_router.include_router(providers.router)
api_router.include_router(configurations.router)
api_router.include_router(configurations.presets_router)
api_router.include_router(prompts.router)
api_router.include_router(emg.router)
api_router.include_router(executions.router)
api_router.include_router(experiments.router)
