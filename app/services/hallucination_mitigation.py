"""Módulo para mitigação de alucinações em VLM.

Implementa estratégias avançadas de prompt engineering e validação
para reduzir alucinações em Vision-Language Models.

Integrado com LangChain para Structured Output e prompt templates.
"""

import re
from collections import Counter
from typing import Any, Optional

import numpy as np
import structlog
from pydantic import BaseModel, Field, validator
from sklearn.metrics.pairwise import cosine_similarity

logger = structlog.get_logger(__name__)


# ============================================================================
# STRUCTURED OUTPUT MODELS
# ============================================================================


class ConfidenceLevel(str):
    """Níveis de confiança permitidos."""

    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"


class ConstructionStatus(str):
    """Status de construção permitidos."""

    COMPLETED = "completed"
    IN_PROGRESS = "in_progress"
    NOT_STARTED = "not_started"
    NOT_VISIBLE = "not_visible"


class DetectedElement(BaseModel):
    """Elemento detectado pela VLM com score de confiança."""

    element_type: str = Field(description="Tipo do elemento (wall, column, beam, slab, foundation)")
    element_name: Optional[str] = Field(None, description="Nome/identificador do elemento do BIM")
    confidence: str = Field(description="Nível de confiança: HIGH, MEDIUM, LOW")
    status: str = Field(description="Status da construção: completed, in_progress, not_started, not_visible")
    description: str = Field(description="Descrição detalhada do elemento observado")
    visible_percentage: Optional[int] = Field(
        None, ge=0, le=100, description="Percentual visível do elemento na imagem (0-100)"
    )
    uncertainty_notes: Optional[str] = Field(None, description="Notas sobre incertezas na identificação")

    @validator("confidence")
    def validate_confidence(cls, v):
        allowed = ["HIGH", "MEDIUM", "LOW"]
        if v.upper() not in allowed:
            raise ValueError(f"Confidence must be one of {allowed}")
        return v.upper()

    @validator("status")
    def validate_status(cls, v):
        allowed = ["completed", "in_progress", "not_started", "not_visible"]
        if v.lower() not in allowed:
            raise ValueError(f"Status must be one of {allowed}")
        return v.lower()


class ViewingConditions(BaseModel):
    """Condições de visualização da imagem."""

    viewing_angle: str = Field(description="Ângulo de visualização (frontal, lateral, aéreo, etc)")
    lighting_quality: str = Field(description="Qualidade da iluminação (excellent, good, poor)")
    image_clarity: str = Field(description="Clareza da imagem (excellent, good, acceptable, poor)")
    obstructions: list[str] = Field(
        default_factory=list, description="Obstruções visíveis (andaimes, equipamentos, etc)"
    )
    occluded_areas: list[str] = Field(default_factory=list, description="Áreas ocluídas ou não visíveis")


class StructuredVLMOutput(BaseModel):
    """Output estruturado completo da análise VLM para BIM."""

    viewing_conditions: ViewingConditions = Field(description="Condições de visualização e limitações")
    elements_detected: list[DetectedElement] = Field(
        default_factory=list, description="Lista de elementos estruturais detectados"
    )
    construction_phase: str = Field(description="Fase da construção (foundation, structure, finishing, completed)")
    overall_quality: str = Field(description="Qualidade geral observada (excellent, good, acceptable, poor)")
    visible_issues: list[str] = Field(
        default_factory=list, description="Problemas ou desvios visíveis (fissuras, desalinhamentos, etc)"
    )
    safety_concerns: list[str] = Field(default_factory=list, description="Preocupações de segurança observadas")
    bim_elements_not_visible: list[str] = Field(
        default_factory=list, description="Elementos esperados do BIM que não são visíveis na imagem"
    )
    confidence_score: float = Field(ge=0.0, le=1.0, description="Score de confiança geral da análise (0.0 a 1.0)")
    analysis_limitations: list[str] = Field(
        default_factory=list, description="Limitações da análise devido a condições de visualização"
    )

    class Config:
        json_schema_extra = {
            "example": {
                "viewing_conditions": {
                    "viewing_angle": "frontal",
                    "lighting_quality": "good",
                    "image_clarity": "good",
                    "obstructions": ["scaffolding on right side"],
                    "occluded_areas": ["foundation level", "interior spaces"],
                },
                "elements_detected": [
                    {
                        "element_type": "column",
                        "element_name": "C-001",
                        "confidence": "HIGH",
                        "status": "completed",
                        "description": "Reinforced concrete column, fully constructed",
                        "visible_percentage": 90,
                    }
                ],
                "construction_phase": "structure",
                "overall_quality": "good",
                "visible_issues": [],
                "safety_concerns": [],
                "bim_elements_not_visible": ["W-105"],
                "confidence_score": 0.85,
                "analysis_limitations": ["Cannot assess interior elements"],
            }
        }


# ============================================================================
# PROMPT TEMPLATES
# ============================================================================


class PromptTemplates:
    """Templates de prompts com diferentes estratégias anti-alucinação."""

    @staticmethod
    def get_confidence_aware_prompt(rag_context: Optional[dict] = None) -> str:
        """Prompt que força indicação de confiança - versão profissional sem emojis."""
        prompt = """You are a professional BIM construction analyst performing a technical site assessment. Conduct your analysis with rigorous attention to detail and evidence-based observations only.

ANALYSIS PROTOCOL:
1. Only describe structural elements that are CLEARLY and UNAMBIGUOUSLY visible in the image
2. Do NOT guess, infer, or assume anything not directly observable
3. If uncertain about ANY aspect, explicitly state the uncertainty and reasoning
4. Indicate confidence level for EVERY observation based on visibility and clarity

CONFIDENCE CLASSIFICATION CRITERIA:
- HIGH: Element is fully visible (>70%), clearly identifiable, distinctive features observable, no ambiguity
- MEDIUM: Element is partially visible (40-70%), somewhat unclear due to viewing angle or obstructions
- LOW: Element is barely visible (<40%), heavily occluded, or identification uncertain due to image limitations

REQUIRED OUTPUT FORMAT:
For each structural element detected:
[Element Type] (Confidence: HIGH/MEDIUM/LOW) (Visible: X%) - Technical description

Examples:
[Column] (Confidence: HIGH) (Visible: 90%) - Reinforced concrete column, approximate dimensions 40x40cm, visible rebar ties at top section, formwork removed
[Wall] (Confidence: MEDIUM) (Visible: 50%) - Appears to be structural wall, approximately 20cm thickness, partially occluded by scaffolding on left side
[Beam] (Confidence: LOW) (Visible: 20%) - Possible beam visible at edge of frame, identification uncertain, requires additional viewing angle for confirmation

"""

        # Adiciona contexto RAG se disponível
        if rag_context and rag_context.get("elements"):
            prompt += "\n\nEXPECTED ELEMENTS FROM BIM MODEL (Reference Only):\n"
            for elem in rag_context["elements"][:5]:
                prompt += (
                    f"- {elem.get('element_type')}: {elem.get('element_name', 'N/A')} - {elem.get('description', '')}\n"
                )
            prompt += "\nIMPORTANT: Only report these elements if they are VISUALLY CONFIRMED in the current image. Expected elements not visible should be listed separately.\n"

        prompt += """
PROHIBITED BEHAVIORS (Critical):
- Do NOT describe typical elements expected in construction sequences unless visually confirmed
- Do NOT infer underground, interior, or occluded elements from exterior/partial views
- Do NOT assume standard dimensions or specifications without visual measurement references
- Do NOT provide definitive statements about partially visible or occluded areas
- Do NOT extrapolate beyond visible image boundaries

REQUIRED BEHAVIORS (Mandatory):
- Use hedging language for uncertain observations: "appears to be", "likely", "possibly", "suggests"
- Explicitly state elements that CANNOT be assessed or are NOT VISIBLE
- Acknowledge viewing angle and image quality limitations
- Differentiate between "confirmed visible", "likely present", "possibly present", and "not visible"
- Note any obstructions (scaffolding, equipment, weather conditions) affecting visibility

Now analyze the construction site image following this protocol precisely:
"""
        return prompt

    @staticmethod
    def get_chain_of_thought_prompt(rag_context: Optional[dict] = None) -> str:
        """Prompt com Chain-of-Thought para reasoning explícito."""
        prompt = """You are a BIM construction analyst. Analyze this image step-by-step.

ANALYSIS STEPS (follow in order):

Step 1: VIEWING CONDITIONS
- Describe the viewing angle, lighting, and image quality
- Identify any obstructions (scaffolding, equipment, etc)
- Note areas that are occluded or unclear

Step 2: ELEMENT IDENTIFICATION
- List only clearly visible structural elements
- For each element, describe what visual features led to identification
- Provide confidence level (HIGH/MEDIUM/LOW) based on visibility

Step 3: CONSTRUCTION STATUS ASSESSMENT
- Evaluate completion status of each identified element
- Base assessment only on visible construction indicators (rebar, formwork, finish, etc)
- Do not assume status for occluded elements

Step 4: BIM CROSS-REFERENCE
"""

        if rag_context and rag_context.get("elements"):
            prompt += "Expected elements from BIM model:\n"
            for elem in rag_context["elements"][:5]:
                prompt += f"  - {elem.get('element_type')}: {elem.get('element_name')}\n"
            prompt += "\nCompare your observations (Step 2) with expected elements.\n"
            prompt += "Mark which expected elements are confirmed vs. not visible.\n\n"

        prompt += """
Step 5: FINAL OUTPUT
Compile structured analysis with:
- Confirmed elements (with confidence scores)
- Expected but not visible elements
- Unexpected elements (if any)
- Uncertainty notes

Now perform the analysis following ALL steps:
"""
        return prompt

    @staticmethod
    def get_negative_constraint_prompt() -> str:
        """Prompt com constraints negativos explícitos - versão profissional."""
        return """You are a professional BIM construction analyst. Perform evidence-based analysis of ONLY what is directly observable in the provided image.

STRICT PROHIBITIONS (Violations will invalidate analysis):
- Do NOT describe elements based on "typical construction sequences" or industry standards
- Do NOT infer underground, interior, or non-visible elements from exterior/partial photographs
- Do NOT assume element dimensions, specifications, or materials without visual measurement references
- Do NOT mention elements commonly present on construction sites unless visibly confirmed in this image
- Do NOT provide definitive statements about partially visible or heavily occluded elements
- Do NOT extrapolate findings beyond the visible boundaries of the current image
- Do NOT describe future construction phases, planned work, or theoretical completions

MANDATORY REPORTING REQUIREMENTS:
- Explicitly state "not visible" or "cannot be assessed" for expected but occluded elements
- Use precise uncertainty markers: "appears to be", "likely", "possibly", "uncertain identification"
- Quantify visibility percentages: "approximately 70% visible", "partially occluded", "minimal visibility"
- Acknowledge assessment limitations: "cannot assess due to viewing angle", "obstructed by equipment"
- Clearly distinguish classification: "confirmed present", "likely present", "possibly present", "not visible", "outside frame"

REQUIRED RESPONSE STRUCTURE:
1. Viewing Conditions Assessment (angle, lighting, obstructions)
2. Confirmed Elements (high confidence, >70% visible)
3. Likely Elements (medium confidence, 40-70% visible)
4. Uncertain Elements (low confidence, <40% visible)
5. Expected BIM Elements NOT VISIBLE in current image
6. Analysis Limitations and Recommendations

Conduct technical site assessment now:
"""


# ============================================================================
# HALLUCINATION DETECTION & MITIGATION
# ============================================================================


class HallucinationMitigator:
    """Estratégias para detectar e mitigar alucinações em VLM."""

    def __init__(self, embedding_service=None):
        self.embedding_service = embedding_service

    def parse_confidence_from_description(self, description: str) -> list[dict]:
        """
        Extrai elementos e scores de confiança da descrição.

        Args:
            description: Descrição gerada pela VLM

        Returns:
            Lista de elementos parseados com confiança
        """
        elements = []

        # Regex para capturar formato: [Element Type] (Confidence: LEVEL) (Visible: X%) - Description
        pattern = r"\[([^\]]+)\]\s*\(Confidence:\s*(HIGH|MEDIUM|LOW)\)\s*(?:\(Visible:\s*(\d+)%\))?\s*-\s*(.+)"

        for line in description.split("\n"):
            match = re.search(pattern, line, re.IGNORECASE)
            if match:
                element_type, confidence, visible_pct, desc = match.groups()

                elements.append(
                    {
                        "element_type": element_type.strip(),
                        "confidence": confidence.upper(),
                        "visible_percentage": int(visible_pct) if visible_pct else None,
                        "description": desc.strip(),
                    }
                )
                logger.debug("element_parsed", element_type=element_type, confidence=confidence)

        if not elements:
            logger.warning("no_structured_elements_found", description_preview=description[:200])

        return elements

    def filter_low_confidence_elements(self, elements: list[dict], threshold: str = "LOW") -> list[dict]:
        """
        Filtra elementos abaixo do threshold de confiança.

        Args:
            elements: Lista de elementos parseados
            threshold: Nível mínimo ('LOW', 'MEDIUM', 'HIGH')

        Returns:
            Elementos filtrados
        """
        confidence_order = {"LOW": 0, "MEDIUM": 1, "HIGH": 2}
        min_level = confidence_order.get(threshold, 0)

        filtered = [e for e in elements if confidence_order.get(e.get("confidence", "LOW"), 0) >= min_level]

        logger.info(
            "confidence_filtering",
            original_count=len(elements),
            filtered_count=len(filtered),
            threshold=threshold,
        )

        return filtered

    async def cross_modal_consistency_check(
        self, image_bytes: bytes, text_description: str, threshold: float = 0.6
    ) -> dict:
        """
        Verifica consistência entre embedding da imagem e da descrição.

        Baixa similaridade pode indicar alucinação.

        Args:
            image_bytes: Bytes da imagem
            text_description: Descrição textual gerada
            threshold: Threshold mínimo de similaridade (0-1)

        Returns:
            Resultado da verificação de consistência
        """
        if not self.embedding_service:
            logger.warning("embedding_service_not_available")
            return {"consistent": None, "similarity": None, "check_performed": False}

        try:
            # Gera embeddings
            image_emb = await self.embedding_service.generate_image_embedding(image_bytes)
            text_emb = await self.embedding_service.generate_embedding(text_description)

            # Calcula similaridade coseno
            image_emb_np = np.array(image_emb).reshape(1, -1)
            text_emb_np = np.array(text_emb).reshape(1, -1)
            similarity = float(cosine_similarity(image_emb_np, text_emb_np)[0][0])

            is_consistent = similarity >= threshold

            if not is_consistent:
                logger.warning(
                    "low_consistency_detected",
                    similarity=similarity,
                    threshold=threshold,
                    description_preview=text_description[:100],
                )

            return {
                "consistent": is_consistent,
                "similarity": round(similarity, 3),
                "threshold": threshold,
                "check_performed": True,
                "recommendation": "Regenerate with stricter constraints" if not is_consistent else "Output validated",
            }

        except Exception as e:
            logger.error("consistency_check_failed", error=str(e))
            return {"consistent": None, "similarity": None, "check_performed": False, "error": str(e)}

    async def verify_against_bim(self, vlm_elements: list[dict], project_id: str, opensearch_client=None) -> dict:
        """
        Verifica se elementos descritos pela VLM existem no modelo BIM.

        Retrieval-Augmented Verification (RAV).

        Args:
            vlm_elements: Elementos extraídos da descrição VLM
            project_id: ID do projeto BIM
            opensearch_client: Cliente OpenSearch para busca

        Returns:
            Resultado da verificação com elementos validados/invalidados
        """
        if not opensearch_client:
            logger.warning("opensearch_client_not_available")
            return {"verification_performed": False}

        verified_elements = []
        hallucinated_elements = []

        for elem in vlm_elements:
            element_type = elem.get("element_type", "")

            try:
                # Busca elemento no OpenSearch
                from app.models.opensearch import BIMElementEmbedding

                # Query por tipo de elemento
                search = BIMElementEmbedding.search()
                search = search.filter("term", project_id=project_id)
                search = search.filter("term", element_type=element_type)

                results = search.execute()

                if results.hits.total.value > 0:
                    # Elemento existe no BIM
                    verified_elements.append(
                        {
                            **elem,
                            "verified": True,
                            "bim_match": {"element_id": results[0].element_id, "description": results[0].description},
                        }
                    )
                    logger.debug("element_verified_in_bim", element_type=element_type)
                else:
                    # Elemento não existe no BIM (possível alucinação)
                    hallucinated_elements.append({**elem, "verified": False, "reason": "Not found in BIM model"})
                    logger.warning("potential_hallucination", element_type=element_type)

            except Exception as e:
                logger.error("bim_verification_error", element_type=element_type, error=str(e))
                verified_elements.append({**elem, "verified": None, "error": str(e)})

        hallucination_rate = len(hallucinated_elements) / len(vlm_elements) if vlm_elements else 0.0

        return {
            "verification_performed": True,
            "total_elements": len(vlm_elements),
            "verified_count": len(verified_elements),
            "hallucinated_count": len(hallucinated_elements),
            "hallucination_rate": round(hallucination_rate, 3),
            "verified_elements": verified_elements,
            "hallucinated_elements": hallucinated_elements,
        }

    async def self_consistency_aggregation(self, descriptions: list[str], consensus_threshold: float = 0.5) -> dict:
        """
        Agrega múltiplas respostas VLM usando votação por maioria.

        Self-Consistency: gera 3+ respostas e mantém apenas elementos
        mencionados em >50% das respostas.

        Args:
            descriptions: Lista de descrições geradas para mesma imagem
            consensus_threshold: Proporção mínima de menções (0-1)

        Returns:
            Elementos com consenso e descrição agregada
        """
        if len(descriptions) < 2:
            logger.warning("self_consistency_requires_multiple_samples", count=len(descriptions))
            return {"consensus_elements": [], "aggregated_description": descriptions[0] if descriptions else ""}

        # Extrai elementos de cada descrição
        all_elements = []
        for desc in descriptions:
            elements = self.parse_confidence_from_description(desc)
            all_elements.extend([e["element_type"] for e in elements])

        # Conta ocorrências
        element_counts = Counter(all_elements)

        # Elementos com consenso (aparecem em >= threshold das respostas)
        min_mentions = int(len(descriptions) * consensus_threshold)
        consensus_elements = [elem for elem, count in element_counts.items() if count >= min_mentions]

        logger.info(
            "self_consistency_aggregation",
            total_samples=len(descriptions),
            unique_elements=len(element_counts),
            consensus_elements=len(consensus_elements),
            threshold=consensus_threshold,
        )

        # Agrega descrições (elementos com consenso)
        aggregated = f"Based on {len(descriptions)} analyses, the following elements were consistently identified:\n"
        for elem in consensus_elements:
            mention_rate = element_counts[elem] / len(descriptions)
            aggregated += f"- {elem} (mentioned in {mention_rate:.0%} of analyses)\n"

        return {
            "consensus_elements": consensus_elements,
            "element_counts": dict(element_counts),
            "aggregated_description": aggregated,
            "total_samples": len(descriptions),
            "consensus_threshold": consensus_threshold,
        }


# ============================================================================
# EVALUATION METRICS
# ============================================================================


class HallucinationMetrics:
    """Métricas para avaliar taxa de alucinação."""

    @staticmethod
    def calculate_precision(detected_elements: list[str], ground_truth: list[str]) -> float:
        """
        Precision: Quantos elementos detectados são reais?

        Args:
            detected_elements: IDs de elementos detectados pela VLM
            ground_truth: IDs de elementos reais (do BIM)

        Returns:
            Precision score (0-1)
        """
        if not detected_elements:
            return 0.0

        true_positives = len(set(detected_elements) & set(ground_truth))
        return true_positives / len(detected_elements)

    @staticmethod
    def calculate_recall(detected_elements: list[str], ground_truth: list[str]) -> float:
        """
        Recall: Quantos elementos reais foram detectados?

        Args:
            detected_elements: IDs de elementos detectados pela VLM
            ground_truth: IDs de elementos reais (do BIM)

        Returns:
            Recall score (0-1)
        """
        if not ground_truth:
            return 0.0

        true_positives = len(set(detected_elements) & set(ground_truth))
        return true_positives / len(ground_truth)

    @staticmethod
    def calculate_hallucination_rate(detected_elements: list[str], ground_truth: list[str]) -> float:
        """
        Taxa de alucinação: Quantos elementos detectados NÃO existem?

        Args:
            detected_elements: IDs de elementos detectados pela VLM
            ground_truth: IDs de elementos reais (do BIM)

        Returns:
            Hallucination rate (0-1)
        """
        if not detected_elements:
            return 0.0

        false_positives = len(set(detected_elements) - set(ground_truth))
        return false_positives / len(detected_elements)

    @staticmethod
    def calculate_f1_score(detected_elements: list[str], ground_truth: list[str]) -> float:
        """
        F1-Score: Média harmônica de precision e recall.

        Args:
            detected_elements: IDs de elementos detectados pela VLM
            ground_truth: IDs de elementos reais (do BIM)

        Returns:
            F1 score (0-1)
        """
        precision = HallucinationMetrics.calculate_precision(detected_elements, ground_truth)
        recall = HallucinationMetrics.calculate_recall(detected_elements, ground_truth)

        if precision + recall == 0:
            return 0.0

        return 2 * (precision * recall) / (precision + recall)

    @staticmethod
    def evaluate_analysis(detected_elements: list[str], ground_truth: list[str]) -> dict:
        """
        Avaliação completa da análise VLM.

        Args:
            detected_elements: Elementos detectados
            ground_truth: Elementos reais

        Returns:
            Todas as métricas calculadas
        """
        return {
            "precision": round(HallucinationMetrics.calculate_precision(detected_elements, ground_truth), 3),
            "recall": round(HallucinationMetrics.calculate_recall(detected_elements, ground_truth), 3),
            "f1_score": round(HallucinationMetrics.calculate_f1_score(detected_elements, ground_truth), 3),
            "hallucination_rate": round(
                HallucinationMetrics.calculate_hallucination_rate(detected_elements, ground_truth), 3
            ),
            "total_detected": len(detected_elements),
            "total_ground_truth": len(ground_truth),
            "true_positives": len(set(detected_elements) & set(ground_truth)),
            "false_positives": len(set(detected_elements) - set(ground_truth)),
            "false_negatives": len(set(ground_truth) - set(detected_elements)),
        }
