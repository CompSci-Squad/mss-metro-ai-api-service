"""Rotas de consulta de progresso e timeline."""

import structlog
from dependency_injector.wiring import inject
from fastapi import APIRouter, HTTPException, status
from pynamodb.exceptions import DoesNotExist

from app.models.dynamodb import AlertModel, BIMProject, ConstructionAnalysisModel

router = APIRouter()
logger = structlog.get_logger(__name__)


@router.get("/progress/{project_id}")
@inject
async def get_project_progress(project_id: str):
    """Retorna progresso e histórico do projeto."""
    try:
        logger.info("consultando_progresso", project_id=project_id)

        # Busca projeto usando ORM
        try:
            project = BIMProject.get(project_id)
        except DoesNotExist:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Projeto não encontrado")

        # Busca análises usando scan com filtro
        analyses = list(ConstructionAnalysisModel.scan(ConstructionAnalysisModel.project_id == project_id))

        # Busca alertas não resolvidos
        alerts = list(AlertModel.scan((AlertModel.project_id == project_id) & ~AlertModel.resolved))

        # Calcula progresso médio
        overall_progress = sum(a.overall_progress for a in analyses) / len(analyses) if analyses else 0.0

        # Última análise
        last_analysis_date = max((a.analyzed_at for a in analyses), default=None) if analyses else None

        return {
            "project_id": project.project_id,
            "project_name": project.project_name,
            "total_analyses": len(analyses),
            "analyses": [
                {
                    "analysis_id": a.analysis_id,
                    "overall_progress": a.overall_progress,
                    "summary": a.summary,
                    "analyzed_at": a.analyzed_at.isoformat() if a.analyzed_at else None,
                }
                for a in analyses
            ],
            "open_alerts": len(alerts),
            "recent_alerts": [
                {
                    "alert_id": alert.alert_id,
                    "alert_type": alert.alert_type,
                    "severity": alert.severity,
                    "title": alert.title,
                    "description": alert.description,
                    "created_at": alert.created_at.isoformat() if alert.created_at else None,
                }
                for alert in alerts[:10]
            ],
            "overall_progress": round(overall_progress, 2),
            "last_analysis_date": last_analysis_date.isoformat() if last_analysis_date else None,
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error("erro_consultar_progresso", error=str(e), exc_info=True)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e)) from e


@router.get("/timeline/{project_id}")
@inject
async def get_project_timeline(project_id: str):
    """Retorna timeline cronológica do projeto."""
    try:
        logger.info("consultando_timeline", project_id=project_id)

        # Busca projeto
        try:
            project = BIMProject.get(project_id)
        except DoesNotExist:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Projeto não encontrado")

        # Busca todas as análises ordenadas por data
        analyses = list(ConstructionAnalysisModel.scan(ConstructionAnalysisModel.project_id == project_id))
        analyses.sort(key=lambda x: x.analyzed_at)

        # Monta timeline
        timeline = []
        for analysis in analyses:
            timeline.append(
                {
                    "timestamp": analysis.analyzed_at.isoformat() if analysis.analyzed_at else None,
                    "analysis_id": analysis.analysis_id,
                    "progress": analysis.overall_progress,
                    "summary": analysis.summary,
                    "image_url": f"s3://{analysis.image_s3_key}",
                    "detected_elements_count": len(analysis.detected_elements),
                    "alerts_count": len(analysis.alerts),
                }
            )

        # Estatísticas de progresso ao longo do tempo
        progress_evolution = []
        for i, analysis in enumerate(analyses):
            progress_evolution.append(
                {"index": i + 1, "date": analysis.analyzed_at.isoformat(), "progress": analysis.overall_progress}
            )

        # Velocidade de progresso (se houver 2+ análises)
        velocity = None
        if len(analyses) >= 2:
            first = analyses[0]
            last = analyses[-1]
            time_diff = (last.analyzed_at - first.analyzed_at).days
            progress_diff = last.overall_progress - first.overall_progress

            if time_diff > 0:
                velocity = round(progress_diff / time_diff, 2)

        return {
            "project_id": project.project_id,
            "project_name": project.project_name,
            "timeline": timeline,
            "progress_evolution": progress_evolution,
            "total_analyses": len(analyses),
            "current_progress": analyses[-1].overall_progress if analyses else 0.0,
            "velocity": velocity,
            "velocity_unit": "% por dia" if velocity else None,
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error("erro_consultar_timeline", error=str(e), exc_info=True)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e)) from e
