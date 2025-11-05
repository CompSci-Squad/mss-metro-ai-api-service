"""Rotas de gerenciamento de alertas e relatórios."""

import structlog
from fastapi import APIRouter, HTTPException, status
from pynamodb.exceptions import DoesNotExist

from app.core.validators import validate_ulid
from app.models.dynamodb import AlertModel, BIMProject, ConstructionAnalysisModel
from app.schemas.bim import Alert, AlertListResponse, AnalysisListResponse, ConstructionAnalysis

router = APIRouter()
logger = structlog.get_logger(__name__)


@router.get("/projects/{project_id}/alerts")
async def list_project_alerts(project_id: str):
    """Lista todos os alertas de um projeto."""
    try:
        validate_ulid(project_id)

        logger.info("listando_alertas", project_id=project_id)

        # Busca projeto para validar
        try:
            BIMProject.get(project_id)
        except DoesNotExist:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Projeto não encontrado") from None

        # Busca todos os alertas do projeto
        alerts = list(
            AlertModel.project_id_index.query(
                project_id,
                scan_index_forward=False,
            )
        )

        # Separa alertas abertos e resolvidos
        open_alerts = [a for a in alerts if not a.resolved]
        resolved_alerts = [a for a in alerts if a.resolved]

        # Converte para schema
        alerts_data = [
            Alert(
                alert_id=a.alert_id,
                project_id=a.project_id,
                analysis_id=a.analysis_id,
                alert_type=a.alert_type,
                severity=a.severity,
                title=a.title,
                description=a.description,
                element_id=a.element_id,
                created_at=a.created_at,
                resolved=a.resolved,
                resolved_at=a.resolved_at,
                resolved_by=a.resolved_by,
            )
            for a in alerts
        ]

        response = AlertListResponse(
            project_id=project_id,
            total_alerts=len(alerts),
            open_alerts=len(open_alerts),
            resolved_alerts=len(resolved_alerts),
            alerts=alerts_data,
        )

        logger.info(
            "alertas_listados",
            project_id=project_id,
            total=len(alerts),
            open=len(open_alerts),
        )

        return response

    except HTTPException:
        raise
    except Exception as e:
        logger.error("erro_listar_alertas", error=str(e), exc_info=True)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e)) from e


@router.get("/projects/{project_id}/reports")
async def list_project_reports(project_id: str, limit: int = 50):
    """Lista todas as análises/relatórios de um projeto."""
    try:
        validate_ulid(project_id)

        logger.info("listando_relatorios", project_id=project_id, limit=limit)

        # Busca projeto
        try:
            project = BIMProject.get(project_id)
        except DoesNotExist:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Projeto não encontrado") from None

        # Busca análises do projeto
        analyses = list(
            ConstructionAnalysisModel.project_id_index.query(
                project_id,
                scan_index_forward=False,
                limit=limit,
            )
        )

        if not analyses:
            return AnalysisListResponse(
                project_id=project_id,
                project_name=project.project_name,
                total_reports=0,
                reports=[],
                latest_progress=None,
            )

        # Converte para schema
        reports = []
        for analysis in analyses:
            # Parse comparison se existir
            comparison_data = None
            if analysis.comparison:
                from app.schemas.bim import AnalysisComparison

                comparison_data = AnalysisComparison(**analysis.comparison)

            report = ConstructionAnalysis(
                analysis_id=analysis.analysis_id,
                project_id=analysis.project_id,
                image_s3_key=analysis.image_s3_key,
                image_description=analysis.image_description,
                detected_elements=analysis.detected_elements,
                overall_progress=analysis.overall_progress,
                summary=analysis.summary,
                alerts=analysis.alerts or [],
                comparison=comparison_data,
                analyzed_at=analysis.analyzed_at,
                processing_time=0.0,
            )
            reports.append(report)

        response = AnalysisListResponse(
            project_id=project_id,
            project_name=project.project_name,
            total_reports=len(reports),
            reports=reports,
            latest_progress=reports[0].overall_progress if reports else None,
        )

        logger.info(
            "relatorios_listados",
            project_id=project_id,
            total=len(reports),
        )

        return response

    except HTTPException:
        raise
    except Exception as e:
        logger.error("erro_listar_relatorios", error=str(e), exc_info=True)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e)) from e
