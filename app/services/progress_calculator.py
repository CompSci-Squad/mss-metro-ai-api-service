"""Serviço para cálculo de progresso de construção."""

import structlog

from app.schemas.bim import ProgressStatus

logger = structlog.get_logger(__name__)


class ProgressCalculator:
    """Serviço responsável por calcular métricas de progresso."""

    def calculate_progress_metrics(self, detected_elements: list[dict], all_elements: list[dict] | None = None, total_elements: int | None = None) -> dict:
        """
        Calcula métricas de progresso da obra.

        Args:
            detected_elements: Elementos detectados na análise
            all_elements: Todos os elementos do projeto BIM (deprecated)
            total_elements: Total de elementos no projeto

        Returns:
            Dicionário com métricas de progresso
        """
        # Usa total_elements se fornecido, senão usa len(all_elements)
        if total_elements is None:
            if not all_elements:
                return {"overall_progress": 0.0}
            total_elements = len(all_elements)
        
        if total_elements == 0:
            return {"overall_progress": 0.0}

        detected_count = len(detected_elements)
        completed_count = sum(1 for e in detected_elements if e.get("status") == ProgressStatus.COMPLETED)
        in_progress_count = sum(1 for e in detected_elements if e.get("status") == ProgressStatus.IN_PROGRESS)

        # Peso: completo = 1.0, em progresso = 0.5
        weighted_progress = (completed_count * 1.0 + in_progress_count * 0.5) / total_elements * 100

        return {
            "overall_progress": round(weighted_progress, 2),
            "detected_count": detected_count,
            "completed_count": completed_count,
            "in_progress_count": in_progress_count,
        }

    def calculate_overall_progress(self, detected_elements: list[dict]) -> float:
        """
        Calcula progresso geral baseado nos elementos detectados.

        Args:
            detected_elements: Lista de elementos detectados

        Returns:
            Progresso percentual (0-100)
        """
        if not detected_elements:
            return 0.0

        total = len(detected_elements)
        completed = sum(1 for e in detected_elements if e.get("status") == ProgressStatus.COMPLETED)
        in_progress = sum(1 for e in detected_elements if e.get("status") == ProgressStatus.IN_PROGRESS)

        # Peso: completo = 1.0, em progresso = 0.5
        weighted = (completed * 1.0 + in_progress * 0.5) / total * 100

        return round(weighted, 2)

    def identify_alerts(self, detected_elements: list[dict], project_data: dict) -> list[str]:
        """
        Identifica alertas baseado na análise.

        Args:
            detected_elements: Elementos detectados
            project_data: Dados do projeto BIM

        Returns:
            Lista de alertas identificados
        """
        alerts = []
        all_elements = project_data.get("elements", [])

        detected_ids = {e.get("element_id") for e in detected_elements}

        for element in all_elements:
            if element["element_id"] not in detected_ids:
                alerts.append(
                    f"{element['element_type']} ({element.get('name', 'sem nome')}) não identificado na imagem"
                )

        for element in detected_elements:
            if element.get("deviation"):
                alerts.append(f"Desvio em {element['element_type']}: {element['deviation']}")

        return alerts
