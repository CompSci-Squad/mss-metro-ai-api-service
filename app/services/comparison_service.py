"""Serviço para comparação temporal de análises."""

import structlog

from app.core.cache_decorator import cache_result
from app.schemas.bim import ProgressStatus
from app.services.progress_calculator import ProgressCalculator
from app.services.vlm_service import VLMService

logger = structlog.get_logger(__name__)


class ComparisonService:
    """Serviço responsável por comparar análises temporais."""

    def __init__(self, vlm_service: VLMService, progress_calculator: ProgressCalculator):
        self.vlm = vlm_service
        self.progress_calculator = progress_calculator

    @cache_result(ttl=600, key_prefix="prev_analysis")
    async def get_previous_analysis(self, project_id: str) -> dict | None:
        """
        Busca a análise mais recente do projeto para comparação.
        Resultado cacheado por 10 minutos.

        Args:
            project_id: ID do projeto

        Returns:
            Dados da análise anterior ou None
        """
        try:
            from app.models.dynamodb import ConstructionAnalysisModel

            # Query usando GSI project_id-analyzed_at-index (ordem decrescente)
            results = list(
                ConstructionAnalysisModel.project_analyzed_index.query(
                    hash_key=project_id,
                    scan_index_forward=False,  # Ordem decrescente (mais recente primeiro)
                    limit=1,
                )
            )

            if not results:
                logger.info("nenhuma_analise_anterior_encontrada", project_id=project_id)
                return None

            previous = results[0]

            # Converte para dict
            previous_data = {
                "analysis_id": previous.analysis_id,
                "analyzed_at": previous.analyzed_at.isoformat() if previous.analyzed_at else None,
                "overall_progress": previous.overall_progress,
                "detected_elements": [e.to_dict() if hasattr(e, "to_dict") else e for e in previous.detected_elements],
                "summary": previous.summary,
            }

            logger.info(
                "analise_anterior_encontrada",
                previous_id=previous.analysis_id,
                previous_progress=previous.overall_progress,
            )

            return previous_data

        except Exception as e:
            logger.warning("erro_buscar_analise_anterior", error=str(e))
            return None

    async def compare_with_previous_analysis(
        self,
        current_elements: list[dict],
        previous_analysis: dict,
        current_description: str,
    ) -> dict:
        """
        Compara análise atual com anterior usando VLM.

        Args:
            current_elements: Elementos detectados atualmente
            previous_analysis: Dados da análise anterior
            current_description: Descrição atual da imagem

        Returns:
            Dicionário com comparação estruturada
        """
        try:
            previous_elements = previous_analysis.get("detected_elements", [])
            previous_progress = previous_analysis.get("overall_progress", 0.0)

            # Calcula progresso atual
            current_progress = self.progress_calculator.calculate_overall_progress(current_elements)
            progress_change = round(current_progress - previous_progress, 2)

            # Identifica elementos novos, removidos e alterados
            current_ids = {e.get("element_id") for e in current_elements if e.get("element_id")}
            previous_ids = {e.get("element_id") for e in previous_elements if e.get("element_id")}

            added_ids = current_ids - previous_ids
            removed_ids = previous_ids - current_ids
            common_ids = current_ids & previous_ids

            # Elementos adicionados
            elements_added = [
                {
                    "element_id": e["element_id"],
                    "element_type": e["element_type"],
                    "change_type": "new",
                    "current_status": e.get("status", ProgressStatus.NOT_STARTED),
                    "description": f"Novo elemento detectado: {e['element_type']}",
                }
                for e in current_elements
                if e.get("element_id") in added_ids
            ]

            # Elementos removidos
            elements_removed = [
                {
                    "element_id": e["element_id"],
                    "element_type": e["element_type"],
                    "change_type": "removed",
                    "previous_status": e.get("status", ProgressStatus.NOT_STARTED),
                    "description": f"Elemento não mais visível: {e['element_type']}",
                }
                for e in previous_elements
                if e.get("element_id") in removed_ids
            ]

            # Elementos com mudança de status
            elements_changed = []
            for curr_elem in current_elements:
                if curr_elem.get("element_id") not in common_ids:
                    continue

                # Busca elemento anterior correspondente
                prev_elem = next(
                    (e for e in previous_elements if e.get("element_id") == curr_elem.get("element_id")), None
                )

                if prev_elem:
                    curr_status = curr_elem.get("status")
                    prev_status = prev_elem.get("status")

                    if curr_status != prev_status:
                        elements_changed.append(
                            {
                                "element_id": curr_elem["element_id"],
                                "element_type": curr_elem["element_type"],
                                "change_type": "status_change",
                                "previous_status": prev_status,
                                "current_status": curr_status,
                                "description": f"Status alterado de {prev_status} para {curr_status}",
                            }
                        )

            # Gera resumo da comparação usando VLM
            comparison_prompt = f"""Compare the current construction analysis with the previous one:

**Previous Analysis:**
- Progress: {previous_progress}%
- Summary: {previous_analysis.get("summary", "N/A")}
- Elements detected: {len(previous_elements)}

**Current Analysis:**
- Progress: {current_progress}%
- Description: {current_description}
- Elements detected: {len(current_elements)}

**Changes:**
- Progress change: {progress_change}%
- New elements: {len(elements_added)}
- Removed elements: {len(elements_removed)}
- Changed elements: {len(elements_changed)}

Provide a concise summary (2-3 sentences) of the construction progress evolution."""

            comparison_summary = await self.vlm.generate_text(comparison_prompt)

            result = {
                "previous_analysis_id": previous_analysis["analysis_id"],
                "previous_timestamp": previous_analysis["analyzed_at"],
                "progress_change": progress_change,
                "elements_added": elements_added,
                "elements_removed": elements_removed,
                "elements_changed": elements_changed,
                "summary": comparison_summary,
            }

            logger.info(
                "comparacao_concluida",
                progress_change=progress_change,
                added=len(elements_added),
                removed=len(elements_removed),
                changed=len(elements_changed),
            )

            return result

        except Exception as e:
            logger.error("erro_comparar_analises", error=str(e))
            # Retorna comparação básica em caso de erro
            return {
                "previous_analysis_id": previous_analysis.get("analysis_id"),
                "previous_timestamp": previous_analysis.get("analyzed_at"),
                "progress_change": 0.0,
                "elements_added": [],
                "elements_removed": [],
                "elements_changed": [],
                "summary": "Erro ao gerar comparação detalhada",
            }
