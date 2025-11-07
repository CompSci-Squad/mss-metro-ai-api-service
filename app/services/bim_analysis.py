"""Serviço de análise BIM com VI-RAG (refatorado)."""

import time

import structlog

from app.services.comparison_service import ComparisonService
from app.services.element_matcher import ElementMatcher
from app.services.embedding_service import EmbeddingService
from app.services.progress_calculator import ProgressCalculator
from app.services.rag_search_service import RAGSearchService
from app.services.vlm_service import VLMService

logger = structlog.get_logger(__name__)


class BIMAnalysisService:
    """Orquestra análise BIM usando VI-RAG delegando responsabilidades para services especializados."""

    def __init__(
        self,
        vlm_service: VLMService,
        embedding_service: EmbeddingService,
        rag_search_service: RAGSearchService,
        element_matcher: ElementMatcher,
        progress_calculator: ProgressCalculator,
        comparison_service: ComparisonService,
    ):
        self.vlm = vlm_service
        self.embedding_service = embedding_service
        self.rag_search = rag_search_service
        self.element_matcher = element_matcher
        self.progress_calc = progress_calculator
        self.comparison = comparison_service

    async def _generate_image_embedding(self, image_bytes: bytes) -> list[float]:
        """Gera embedding da imagem usando CLIP."""
        try:
            embedding = await self.embedding_service.generate_image_embedding(image_bytes)
            logger.info("image_embedding_gerado", embedding_dim=len(embedding))
            return embedding
        except Exception as e:
            logger.error("erro_gerar_embedding_imagem", error=str(e))
            raise

    async def analyze_construction_image(
        self,
        image_bytes: bytes,
        project_data: dict,
        target_element_ids: list[str] | None = None,
        context: str | None = None,
    ) -> dict:
        """
        Analisa imagem da obra e compara com modelo BIM usando busca vetorial.

        Args:
            image_bytes: Bytes da imagem
            project_data: Dados do projeto BIM (elementos esperados)
            target_element_ids: IDs específicos para análise
            context: Contexto adicional

        Returns:
            Resultado estruturado da análise
        """
        try:
            start_time = time.time()

            logger.info(
                "iniciando_analise_bim",
                project_id=project_data.get("project_id"),
                total_elements=project_data.get("total_elements"),
            )

            # 1. Gera embedding da imagem (para RAG context)
            image_embedding = await self._generate_image_embedding(image_bytes)

            # 2. Busca contexto RAG usando embedding da imagem
            rag_context = await self.rag_search.fetch_rag_context(
                image_embedding, project_data.get("project_id"), top_k=5
            )

            # 3. Gera descrição da imagem usando VLM + RAG context
            description = await self._generate_image_description(image_bytes, context, rag_context)

            # 4. Gera embedding da descrição
            description_embedding = await self.embedding_service.generate_embedding(description)

            # 5. Busca vetorial de elementos similares
            vector_matches = await self.rag_search.find_similar_elements_vector(
                project_data.get("project_id"),
                description_embedding,
                target_element_ids,
            )

            # 6. Matching por keywords (fallback)
            keyword_matches = await self.element_matcher.compare_with_bim_model(
                description, project_data, target_element_ids
            )

            # 7. Combina resultados (vetorial + keywords)
            detected_elements = self.element_matcher.merge_detection_results(
                vector_matches, keyword_matches["detected_elements"]
            )

            # 8. Calcula métricas de progresso
            progress_metrics = self.progress_calc.calculate_progress_metrics(
                detected_elements, project_data.get("elements", [])
            )

            # 9. Identifica alertas
            alerts = self.progress_calc.identify_alerts(detected_elements, project_data)

            processing_time = time.time() - start_time

            result = {
                "detected_elements": detected_elements,
                "overall_progress": progress_metrics["overall_progress"],
                "summary": description,
                "alerts": alerts,
                "processing_time": round(processing_time, 2),
            }

            logger.info(
                "analise_bim_concluida",
                progress=progress_metrics["overall_progress"],
                detected=len(detected_elements),
                alerts=len(alerts),
                processing_time=processing_time,
            )

            return result

        except Exception as e:
            logger.error("erro_analise_bim", error=str(e), exc_info=True)
            raise

    async def _generate_image_description(
        self, image_bytes: bytes, context: str | None = None, rag_context: dict | None = None
    ) -> str:
        """Gera descrição textual da imagem usando VLM com contexto RAG."""
        try:
            # Constrói prompt com RAG context para reduzir alucinações
            prompt = """You are a BIM construction analyst. Analyze ONLY what you can clearly see in the image.

RULES:
- Only describe elements that are VISIBLY PRESENT in the image
- Do NOT infer or assume elements that are not clearly visible
- Use SPECIFIC measurements and quantities when visible
- Focus on structural elements: walls, columns, slabs, beams, foundations
- Indicate construction status: completed, in-progress, or not started
"""

            # Adiciona contexto RAG (elementos esperados do BIM)
            if rag_context and rag_context.get("elements"):
                prompt += "\n\nEXPECTED ELEMENTS (from BIM model):\n"
                for elem in rag_context["elements"][:5]:  # Top 5 mais relevantes
                    prompt += f"- {elem.get('element_type')}: {elem.get('element_name', 'N/A')} - {elem.get('description', '')}\n"
                prompt += "\nOnly mention these elements if you can CLEARLY identify them in the image.\n"

            # Few-shot examples para guiar formato de resposta
            prompt += """\n\nEXAMPLE OUTPUT FORMAT:
"The image shows 3 reinforced concrete columns in the foundation phase. Two columns appear completed with visible rebar ties. One column is partially constructed, approximately 60% complete. The foundation slab is visible beneath, fully poured and cured. No walls or beams are visible in this view."

Now analyze the provided construction image:"""

            if context:
                prompt += f"\n\nAdditional context: {context}"

            # Usa VLMService existente
            description = await self.vlm.generate_caption(image_bytes, prompt)

            # Post-processing: remove respostas muito genéricas
            if len(description) < 30:
                logger.warning("descricao_muito_curta", length=len(description))
                description += " [Low confidence - insufficient detail]"

            logger.info("descricao_gerada", length=len(description), has_rag_context=bool(rag_context))
            return description

        except Exception as e:
            logger.error("erro_gerar_descricao", error=str(e))
            raise

    async def get_previous_analysis(self, project_id: str) -> dict | None:
        """Delega para ComparisonService."""
        return await self.comparison.get_previous_analysis(project_id)

    async def compare_with_previous_analysis(
        self, current_elements: list[dict], previous_analysis: dict, current_description: str
    ) -> dict:
        """Delega para ComparisonService."""
        return await self.comparison.compare_with_previous_analysis(
            current_elements, previous_analysis, current_description
        )
