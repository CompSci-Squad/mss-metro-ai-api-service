"""Rotas de consulta de progresso e timeline."""

import structlog
from dependency_injector.wiring import inject
from fastapi import APIRouter, HTTPException, status
from pynamodb.exceptions import DoesNotExist

from app.models.dynamodb import AlertModel, BIMProject, ConstructionAnalysisModel

router = APIRouter()
logger = structlog.get_logger(__name__)


@router.get(
    "/progress/{project_id}",
    tags=["Progresso"],
    summary="Progresso do projeto",
    responses={
        200: {
            "description": "Progresso retornado com sucesso",
            "content": {
                "application/json": {
                    "example": {
                        "project_id": "01HXYZ123ABC",
                        "project_name": "Edifício Residencial ABC",
                        "total_analyses": 5,
                        "analyses": [
                            {
                                "analysis_id": "01HXYZ456DEF",
                                "overall_progress": 67.5,
                                "summary": "3 pilares completos, 2 vigas em andamento",
                                "analyzed_at": "2024-11-07T14:20:00Z"
                            },
                            {
                                "analysis_id": "01HXYZ789GHI",
                                "overall_progress": 55.0,
                                "summary": "Estrutura inicial em andamento",
                                "analyzed_at": "2024-11-05T10:30:00Z"
                            }
                        ],
                        "open_alerts": 3,
                        "recent_alerts": [
                            {
                                "alert_id": "01HXYZ999XXX",
                                "alert_type": "missing_element",
                                "severity": "medium",
                                "title": "Elemento não detectado",
                                "description": "IfcWall (Parede Norte) não identificado",
                                "created_at": "2024-11-07T14:20:30Z"
                            }
                        ],
                        "overall_progress": 61.25,
                        "last_analysis_date": "2024-11-07T14:20:00Z"
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
                    "example": {"detail": "Erro ao consultar progresso"}
                }
            }
        }
    }
)
@inject
async def get_project_progress(project_id: str):
    """Retorna progresso atual, histórico de análises e alertas do projeto."""
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


@router.get(
    "/timeline/{project_id}",
    tags=["Progresso"],
    summary="Timeline do projeto",
    description="""
    Retorna timeline cronológica completa do projeto com evolução do progresso.
    
    ## 📅 Timeline
    
    Ordenação cronológica de todas as análises:
    - Timestamp de cada análise
    - Progresso percentual
    - Resumo textual
    - Link da imagem no S3
    - Elementos detectados e alertas
    
    ## 📈 Evolução do Progresso
    
    Array com progresso ao longo do tempo:
    ```json
    "progress_evolution": [
        {"index": 1, "date": "2024-11-01", "progress": 25.0},
        {"index": 2, "date": "2024-11-03", "progress": 45.0},
        {"index": 3, "date": "2024-11-05", "progress": 67.5}
    ]
    ```
    
    ## 💨 Velocidade do Progresso
    
    Se houver 2+ análises, calcula velocidade média:
    ```
    velocidade = (progresso_final - progresso_inicial) / dias_decorridos
    ```
    
    **Exemplo**: 40% em 20 dias = 2% por dia
    
    ## 📊 Gráfico Sugerido
    
    Use `progress_evolution` para gerar gráfico de linha mostrando evolução.
    """,
    responses={
        200: {
            "description": "Timeline retornada com sucesso",
            "content": {
                "application/json": {
                    "example": {
                        "project_id": "01HXYZ123ABC",
                        "project_name": "Edifício Residencial ABC",
                        "timeline": [
                            {
                                "timestamp": "2024-11-01T09:00:00Z",
                                "analysis_id": "01HXYZ111AAA",
                                "progress": 25.0,
                                "summary": "Fundação iniciada",
                                "image_url": "s3://bim-projects/01HXYZ123ABC/images/01HXYZ111AAA.jpg",
                                "detected_elements_count": 12,
                                "alerts_count": 1
                            },
                            {
                                "timestamp": "2024-11-05T14:30:00Z",
                                "analysis_id": "01HXYZ789GHI",
                                "progress": 55.0,
                                "summary": "Estrutura em andamento",
                                "image_url": "s3://bim-projects/01HXYZ123ABC/images/01HXYZ789GHI.jpg",
                                "detected_elements_count": 28,
                                "alerts_count": 2
                            },
                            {
                                "timestamp": "2024-11-07T14:20:00Z",
                                "analysis_id": "01HXYZ456DEF",
                                "progress": 67.5,
                                "summary": "3 pilares completos, 2 vigas em andamento",
                                "image_url": "s3://bim-projects/01HXYZ123ABC/images/01HXYZ456DEF.jpg",
                                "detected_elements_count": 35,
                                "alerts_count": 3
                            }
                        ],
                        "progress_evolution": [
                            {"index": 1, "date": "2024-11-01T09:00:00Z", "progress": 25.0},
                            {"index": 2, "date": "2024-11-05T14:30:00Z", "progress": 55.0},
                            {"index": 3, "date": "2024-11-07T14:20:00Z", "progress": 67.5}
                        ],
                        "total_analyses": 3,
                        "current_progress": 67.5,
                        "velocity": 7.08,
                        "velocity_unit": "% por dia"
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
                    "example": {"detail": "Erro ao consultar timeline"}
                }
            }
        }
    }
)
@inject
async def get_project_timeline(project_id: str):
    """Retorna timeline cronológica completa com evolução do progresso."""
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
