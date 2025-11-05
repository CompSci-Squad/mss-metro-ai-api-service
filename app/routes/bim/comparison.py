"""Rotas de comparação entre análises."""

import structlog
from dependency_injector.wiring import inject
from fastapi import APIRouter, HTTPException, status
from pynamodb.exceptions import DoesNotExist

from app.models.dynamodb import BIMProject, ConstructionAnalysisModel

router = APIRouter()
logger = structlog.get_logger(__name__)


@router.get("/compare/{project_id}")
@inject
async def compare_analyses(project_id: str, analysis_ids: str):
    """
    Compara múltiplas análises lado a lado.

    Args:
        project_id: ID do projeto
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
