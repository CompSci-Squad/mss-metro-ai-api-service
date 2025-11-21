"""Structured Output simplificado para VLM."""

import json
import re

import structlog

from app.services.hallucination_mitigation import PromptTemplates, StructuredVLMOutput
from app.services.vlm_service import VLMService

logger = structlog.get_logger(__name__)


class VLMStructuredOutput:
    def __init__(self, vlm_service: VLMService | None = None):
        self.vlm = vlm_service or VLMService()
        self.prompt_templates = PromptTemplates()

    async def analyze(
        self,
        image_bytes: bytes,
        rag_context: dict | None = None,
        prompt_strategy: str = "confidence_aware",
        max_retries: int = 2,
    ) -> StructuredVLMOutput | None:
        prompt = self._get_prompt(prompt_strategy, rag_context)
        prompt += "\n\n" + self._get_json_instructions()

        for attempt in range(max_retries + 1):
            try:
                output = await self._generate(image_bytes, prompt)
                structured = self._parse_json(output)
                if structured:
                    logger.info("structured_output_success", attempt=attempt + 1)
                    return structured
            except Exception as e:
                logger.error("vlm_error", error=str(e), attempt=attempt + 1)

        return None

    def _get_prompt(self, strategy: str, rag_context: dict | None) -> str:
        if strategy == "confidence_aware":
            return self.prompt_templates.get_confidence_aware_prompt(rag_context)
        if strategy == "chain_of_thought":
            return self.prompt_templates.get_chain_of_thought_prompt(rag_context)
        return self.prompt_templates.get_negative_constraint_prompt()

    def _get_json_instructions(self) -> str:
        return """OUTPUT AS JSON:
{
    "viewing_conditions": {"viewing_angle": "str", "lighting_quality": "str", "image_clarity": "str"},
    "elements_detected": [{"element_type": "str", "confidence": "HIGH|MEDIUM|LOW", "status": "str", "description": "str"}],
    "confidence_score": 0.0-1.0
}"""

    async def _generate(self, image_bytes: bytes, prompt: str) -> str:
        """
        Generate VLM output using text-only model.
        
        NOTA: Modelo GGUF é text-only. Para análise com contexto de imagem,
        considere extrair contexto via embeddings primeiro.
        """
        # Por enquanto, usa prompt direto (sem contexto visual)
        # TODO: Extrair contexto visual via embeddings se necessário
        logger.warning(
            "vlm_structured_output_text_only",
            message="Usando modelo text-only sem contexto visual direto"
        )
        return await self.vlm.generate_text(prompt)

    def _parse_json(self, output: str) -> StructuredVLMOutput | None:
        try:
            json_match = re.search(r"\{.*\}", output, re.DOTALL)
            if not json_match:
                return None

            data = json.loads(json_match.group(0))

            # Adiciona defaults para campos opcionais
            defaults = {
                "construction_phase": "unknown",
                "overall_quality": "acceptable",
                "visible_issues": [],
                "safety_concerns": [],
                "bim_elements_not_visible": [],
                "analysis_limitations": []
            }
            data = {**defaults, **data}

            return StructuredVLMOutput(**data)
        except Exception as e:
            logger.error("json_parse_error", error=str(e), output_preview=output[:200])
            return None
