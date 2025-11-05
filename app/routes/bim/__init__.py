"""Rotas VIRAG-BIM - Estrutura modular."""

from fastapi import APIRouter

from . import alerts, analysis, comparison, progress, projects

router = APIRouter(prefix="/bim", tags=["VIRAG-BIM"])

# Agrega todos os sub-routers
router.include_router(projects.router)
router.include_router(analysis.router)
router.include_router(progress.router)
router.include_router(comparison.router)
router.include_router(alerts.router)
