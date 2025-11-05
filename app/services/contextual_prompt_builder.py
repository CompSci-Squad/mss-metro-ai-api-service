"""Prompts contextuais com histórico de análises (virag_analyses)."""

from datetime import datetime

import structlog

from app.models.dynamodb import ConstructionAnalysisModel
from app.services.hallucination_mitigation import PromptTemplates

logger = structlog.get_logger(__name__)


class ContextualPromptBuilder:
    def __init__(self, enable_contextual: bool = True):
        self.enable_contextual = enable_contextual
        self.prompt_templates = PromptTemplates()

    async def build_prompt(
        self, project_id: str, rag_context: dict | None = None, prompt_strategy: str = "confidence_aware"
    ) -> str:
        base_prompt = self._get_base_prompt(prompt_strategy, rag_context)

        if not self.enable_contextual:
            return base_prompt

        try:
            previous = await self._get_previous_analysis(project_id)
            if previous:
                return base_prompt + "\n\n" + self._build_temporal_context(previous)
        except Exception as e:
            logger.warning("contextual_prompt_error", error=str(e))

        return base_prompt

    def _get_base_prompt(self, strategy: str, rag_context: dict | None) -> str:
        templates = {
            "confidence_aware": lambda: self.prompt_templates.get_confidence_aware_prompt(rag_context),
            "chain_of_thought": lambda: self.prompt_templates.get_chain_of_thought_prompt(rag_context),
            "negative_constraint": lambda: self.prompt_templates.get_negative_constraint_prompt(),
        }
        return templates.get(strategy, templates["confidence_aware"])()

    async def _get_previous_analysis(self, project_id: str) -> dict | None:
        try:
            analyses = list(
                ConstructionAnalysisModel.project_id_index.query(project_id, scan_index_forward=False, limit=1)
            )

            if not analyses:
                return None

            a = analyses[0]
            return {
                "timestamp": a.analyzed_at,
                "overall_progress": float(a.overall_progress),
                "detected_elements": [self._parse_element(e) for e in (a.detected_elements or [])],
                "construction_phase": self._infer_phase(float(a.overall_progress)),
            }
        except Exception as e:
            logger.error("fetch_previous_error", error=str(e))
            return None

    def _parse_element(self, elem) -> dict:
        return (
            elem
            if isinstance(elem, dict)
            else {
                "element_name": elem.get("element_name") or elem.get("element_id"),
                "element_type": elem.get("element_type"),
                "status": elem.get("status"),
            }
        )

    def _infer_phase(self, progress: float) -> str:
        if progress < 25:
            return "foundation"
        if progress < 60:
            return "structure"
        if progress < 90:
            return "finishing"
        return "completed"

    def _build_temporal_context(self, prev: dict) -> str:
        days = self._calculate_days_since(prev)
        elements = prev.get("detected_elements", [])

        completed = [e for e in elements if e.get("status") == "completed"]
        in_progress = [e for e in elements if e.get("status") == "in_progress"]

        context = f"""PREVIOUS ANALYSIS ({days} days ago):
Progress: {prev.get("overall_progress")}% | Phase: {prev.get("construction_phase")}
"""

        if completed:
            context += "\nCOMPLETED: " + ", ".join([e.get("element_name", "?") for e in completed[:5]])
        if in_progress:
            context += "\nIN PROGRESS: " + ", ".join([e.get("element_name", "?") for e in in_progress[:5]])

        context += f"""\n\nFOCUS:
1. Verify IN PROGRESS elements are now COMPLETED
2. Identify NEW elements
3. Confirm COMPLETED elements remain completed
4. Expected progress: +{min(days * 2, 20):.0f}% based on {days} days
"""
        return context

    def _calculate_days_since(self, prev: dict) -> int:
        try:
            ts = prev.get("timestamp")
            prev_date = datetime.fromisoformat(ts.replace("Z", "+00:00")) if isinstance(ts, str) else ts
            return (datetime.now() - prev_date).days if prev_date else 0
        except:
            return 0
