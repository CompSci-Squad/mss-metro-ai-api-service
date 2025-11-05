"""Structured Output simplificado para VLM."""

import json
import re

import structlog
import torch
from PIL import Image

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
        import io
        
        image = Image.open(io.BytesIO(image_bytes)).convert("RGB")
        inputs = self.vlm.processor(image, text=prompt, return_tensors="pt")

        if self.vlm.device != "cpu":
            inputs = {k: v.to(self.vlm.device) for k, v in inputs.items()}

        with torch.no_grad():
            generated_ids = self.vlm.model.generate(**inputs, max_length=500, num_beams=5, do_sample=False)

        return self.vlm.processor.batch_decode(generated_ids, skip_special_tokens=True)[0].strip()

    def _parse_json(self, output: str) -> StructuredVLMOutput | None:
        try:
            json_match = re.search(r'\{.*\}', output, re.DOTALL)
            if not json_match:
                return None

            data = json.loads(json_match.group(0))
            return StructuredVLMOutput(**data)
        except Exception as e:
            logger.error("json_parse_error", error=str(e))
            return None
