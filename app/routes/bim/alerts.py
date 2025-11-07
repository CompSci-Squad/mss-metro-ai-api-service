"""Rotas de gerenciamento de alertas e relatórios."""

import structlog
from fastapi import APIRouter, HTTPException, status
from pynamodb.exceptions import DoesNotExist

from app.core.validators import validate_ulid
from app.models.dynamodb import AlertModel, BIMProject, ConstructionAnalysisModel
from app.schemas.bim import Alert, AlertListResponse, AnalysisListResponse, ConstructionAnalysis

router = APIRouter()
logger = structlog.get_logger(__name__)


@router.get(
    "/projects/{project_id}/alerts",
    tags=["Alertas"],
    summary="Listar alertas do projeto",
    responses={
        200: {
            "description": "Alertas listados com sucesso",
            "content": {
                "application/json": {
                    "example": {
                        "project_id": "01HXYZ123ABC",
                        "total_alerts": 8,
                        "open_alerts": 3,
                        "resolved_alerts": 5,
                        "alerts": [
                            {
                                "alert_id": "01HXYZ999XXX",
                                "project_id": "01HXYZ123ABC",
                                "analysis_id": "01HXYZ456DEF",
                                "alert_type": "missing_element",
                                "severity": "medium",
                                "title": "Elemento não detectado",
                                "description": "IfcWall (Parede Norte) não identificado na imagem",
                                "element_id": "2O2Fr$t4X7Zf8NOew3FLOH",
                                "created_at": "2024-11-07T14:20:30Z",
                                "resolved": False,
                                "resolved_at": None,
                                "resolved_by": None
                            },
                            {
                                "alert_id": "01HXYZ888YYY",
                                "project_id": "01HXYZ123ABC",
                                "analysis_id": "01HXYZ789GHI",
                                "alert_type": "quality_issue",
                                "severity": "high",
                                "title": "Possível desvio na estrutura",
                                "description": "Pilar parece desalinhado",
                                "element_id": "3P3Gs$u5Y8Ag9OPfx4GMPI",
                                "created_at": "2024-11-05T14:30:45Z",
                                "resolved": True,
                                "resolved_at": "2024-11-06T09:15:00Z",
                                "resolved_by": "engenheiro@example.com"
                            }
                        ]
                    }
                }
            }
        },
        404: {
            "description": "Projeto não encontrado",
            "content": {
                "application/json": {
                    "example": {"detail": "Projeto não encontrado"}
                }
            }
        },
        500: {
            "description": "Erro interno",
            "content": {
                "application/json": {
                    "example": {"detail": "Erro ao listar alertas"}
                }
            }
        }
    }
)
async def list_project_alerts(project_id: str):
    """Lista todos os alertas de um projeto (abertos e resolvidos)."""
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


@router.get(
    "/projects/{project_id}/reports",
    tags=["Alertas"],
    summary="Listar relatórios/análises",
    responses={
        200: {
            "description": "Relatórios listados com sucesso",
            "content": {
                "application/json": {
                    "example": {
                        "project_id": "01HXYZ123ABC",
                        "project_name": "Edifício Residencial ABC",
                        "total_reports": 5,
                        "latest_progress": 67.5,
                        "reports": [
                            {
                                "analysis_id": "01HXYZ456DEF",
                                "project_id": "01HXYZ123ABC",
                                "image_s3_key": "bim-projects/01HXYZ123ABC/images/01HXYZ456DEF.jpg",
                                "image_description": "Estrutura de concreto - pilares e vigas",
                                "detected_elements": [
                                    {
                                        "element_id": "2O2Fr$t4X7Zf8NOew3FLOH",
                                        "element_type": "IfcColumn",
                                        "confidence": 0.89,
                                        "status": "completed",
                                        "description": "Pilar detectado",
                                        "deviation": None
                                    }
                                ],
                                "overall_progress": 67.5,
                                "summary": "3 pilares completos, 2 vigas em andamento",
                                "alerts": ["Parede Norte não detectada"],
                                "comparison": {
                                    "previous_analysis_id": "01HXYZ789GHI",
                                    "progress_change": 12.5,
                                    "summary": "Progresso de 12.5%"
                                },
                                "analyzed_at": "2024-11-07T14:20:00Z",
                                "processing_time": 0.0
                            },
                            {
                                "analysis_id": "01HXYZ789GHI",
                                "project_id": "01HXYZ123ABC",
                                "image_s3_key": "bim-projects/01HXYZ123ABC/images/01HXYZ789GHI.jpg",
                                "image_description": "Vista geral da estrutura",
                                "detected_elements": [],
                                "overall_progress": 55.0,
                                "summary": "Estrutura inicial em andamento",
                                "alerts": [],
                                "comparison": None,
                                "analyzed_at": "2024-11-05T10:30:00Z",
                                "processing_time": 0.0
                            }
                        ]
                    }
                }
            }
        },
        404: {
            "description": "Projeto não encontrado",
            "content": {
                "application/json": {
                    "example": {"detail": "Projeto não encontrado"}
                }
            }
        },
        500: {
            "description": "Erro interno",
            "content": {
                "application/json": {
                    "example": {"detail": "Erro ao listar relatórios"}
                }
            }
        }
    }
)
async def list_project_reports(project_id: str, limit: int = 50):
    """Lista todas as análises/relatórios de um projeto (ordenados por data)."""
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
