"""Rotas de comparação entre análises."""

import structlog
from dependency_injector.wiring import inject
from fastapi import APIRouter, HTTPException, status
from pynamodb.exceptions import DoesNotExist

from app.models.dynamodb import BIMProject, ConstructionAnalysisModel

router = APIRouter()
logger = structlog.get_logger(__name__)


@router.get(
    "/compare/{project_id}",
    tags=["Comparação"],
    summary="Comparar múltiplas análises",
    responses={
        200: {
            "description": "Comparação realizada com sucesso",
            "content": {
                "application/json": {
                    "example": {
                        "project_id": "01HXYZ123ABC",
                        "project_name": "Edifício Residencial ABC",
                        "comparisons": [
                            {
                                "analysis_id": "01HXYZ111AAA",
                                "timestamp": "2024-11-01T09:00:00Z",
                                "progress": 25.0,
                                "summary": "Fundação iniciada",
                                "detected_elements": ["elem1", "elem2"],
                                "alerts": ["alerta1"]
                            },
                            {
                                "analysis_id": "01HXYZ789GHI",
                                "timestamp": "2024-11-05T14:30:00Z",
                                "progress": 55.0,
                                "summary": "Estrutura em andamento",
                                "detected_elements": ["elem1", "elem2", "elem3"],
                                "alerts": ["alerta1", "alerta2"]
                            },
                            {
                                "analysis_id": "01HXYZ456DEF",
                                "timestamp": "2024-11-07T14:20:00Z",
                                "progress": 67.5,
                                "summary": "3 pilares completos",
                                "detected_elements": ["elem1", "elem2", "elem3", "elem4"],
                                "alerts": ["alerta1", "alerta2", "alerta3"]
                            }
                        ],
                        "differences": [
                            {
                                "from": "01HXYZ111AAA",
                                "to": "01HXYZ789GHI",
                                "progress_change": 30.0,
                                "new_alerts": 1
                            },
                            {
                                "from": "01HXYZ789GHI",
                                "to": "01HXYZ456DEF",
                                "progress_change": 12.5,
                                "new_alerts": 1
                            }
                        ]
                    }
                }
            }
        },
        404: {
            "description": "Projeto ou análises não encontradas",
            "content": {
                "application/json": {
                    "examples": {
                        "project_not_found": {
                            "summary": "Projeto não encontrado",
                            "value": {"detail": "Projeto não encontrado"}
                        },
                        "no_analyses": {
                            "summary": "Nenhuma análise encontrada",
                            "value": {"detail": "Nenhuma análise encontrada"}
                        }
                    }
                }
            }
        },
        500: {
            "description": "Erro interno",
            "content": {
                "application/json": {
                    "example": {"detail": "Erro ao comparar análises"}
                }
            }
        }
    }
)
@inject
async def compare_analyses(project_id: str, analysis_ids: str):
    """
    Compara múltiplas análises lado a lado.

    Args:
        project_id: ID do projeto (ULID)
        analysis_ids: IDs das análises separados por vírgula (ex: "id1,id2,id3")
    """
    try:
        logger.info("comparando_analises", project_id=project_id, analysis_ids=analysis_ids)

        # Busca projeto
        try:
            project = BIMProject.get(project_id)
        except DoesNotExist:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Projeto não encontrado")

        # Parse IDs
        ids = [aid.strip() for aid in analysis_ids.split(",")]

        # Busca análises
        comparisons = []
        for analysis_id in ids:
            try:
                analysis = ConstructionAnalysisModel.get(analysis_id)

                comparisons.append(
                    {
                        "analysis_id": analysis.analysis_id,
                        "timestamp": analysis.analyzed_at.isoformat() if analysis.analyzed_at else None,
                        "progress": analysis.overall_progress,
                        "summary": analysis.summary,
                        "detected_elements": analysis.detected_elements,
                        "alerts": analysis.alerts,
                    }
                )
            except DoesNotExist:
                logger.warning("analise_nao_encontrada", analysis_id=analysis_id)
                continue

        if not comparisons:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Nenhuma análise encontrada")

        # Ordena por data
        comparisons.sort(key=lambda x: x["timestamp"] if x["timestamp"] else "")

        # Calcula diferenças
        differences = []
        if len(comparisons) >= 2:
            for i in range(1, len(comparisons)):
                prev = comparisons[i - 1]
                curr = comparisons[i]

                progress_diff = curr["progress"] - prev["progress"]
                new_alerts = len(curr["alerts"]) - len(prev["alerts"])

                differences.append(
                    {
                        "from": prev["analysis_id"],
                        "to": curr["analysis_id"],
                        "progress_change": round(progress_diff, 2),
                        "new_alerts": new_alerts,
                    }
                )

        return {
            "project_id": project.project_id,
            "project_name": project.project_name,
            "comparisons": comparisons,
            "differences": differences,
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error("erro_comparar_analises", error=str(e), exc_info=True)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e)) from e
