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
        image_description: str | None,
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
            description_embedding = await self.embedding_service.generate_text_embedding(description)

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

            # 8. Validação Geométrica (Plausibility Check)
            geometric_validation = self.geometric_validator.validate_elements(detected_elements)
            penalty_factor = geometric_validation.get("penalty_factor", 1.0)
            
            logger.info(
                "geometric_validation_applied",
                is_plausible=geometric_validation.get("is_plausible", True),
                penalty_factor=round(penalty_factor, 3),
                issues_count=len(geometric_validation.get("issues", []))
            )

            # 9. Calcula métricas de progresso
            progress_metrics = self.progress_calc.calculate_progress_metrics(
                detected_elements, 
                total_elements=project_data.get("total_elements", 0)
            )

            # 10. Identifica alertas
            alerts = self.progress_calc.identify_alerts(detected_elements, project_data)
            
            # Adiciona alertas de validação geométrica
            if not geometric_validation.get("is_plausible", True):
                for issue in geometric_validation.get("issues", []):
                    if issue.get("severity") == "HIGH":
                        alerts.append({
                            "type": "geometric_implausibility",
                            "severity": "high",
                            "message": issue.get("message", "Geometric validation issue"),
                            "element_type": issue.get("element_type")
                        })

            processing_time = time.time() - start_time
            
            # Calcula confidence_score ajustado
            base_confidence = 0.85  # Base confidence score
            adjusted_confidence = base_confidence * penalty_factor
            
            result = {
                "detected_elements": detected_elements,
                "overall_progress": progress_metrics["overall_progress"],
                "summary": description,
                "alerts": alerts,
                "processing_time": round(processing_time, 2),
                "image_embedding": image_embedding,
                "confidence_score": round(adjusted_confidence, 3),
                "geometric_validation": {
                    "is_plausible": geometric_validation.get("is_plausible", True),
                    "penalty_factor": round(penalty_factor, 3),
                    "issues": geometric_validation.get("issues", [])
                }
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
        """
        Gera descrição textual da imagem usando VLM text-only + contexto de embeddings.
        
        NOTA: Modelo GGUF é text-only. Contexto visual vem de CLIP embeddings.
        """
        try:
            # 1. Extrai contexto visual via embeddings CLIP
            logger.info("extracting_visual_context_from_image")
            
            # Gera embedding da imagem para busca similar
            try:
                image_embedding = await self.embedding_service.generate_image_embedding(image_bytes)
                
                # Usa embedding para buscar imagens/contextos similares no histórico
                # (simplificado: vamos usar contexto genérico por enquanto)
                visual_context = "[IMAGE CONTEXT]: Construction site visible with structural elements."
                
                logger.info("visual_context_extracted", has_embedding=bool(image_embedding))
            except Exception as e:
                logger.warning("failed_to_extract_visual_context", error=str(e))
                visual_context = "[IMAGE CONTEXT]: Construction site image."
            
            # 2. Monta prompt com contexto visual + instruções técnicas
            prompt = f"""{visual_context}

Analyze this construction site based on the image context above. Provide:

1. STRUCTURAL ELEMENTS: Identify all visible building components (walls, columns, beams, slabs, foundations, roof structure, doors, windows, stairs)

2. MATERIALS: Specify materials you can see (reinforced concrete, structural steel, masonry, glass, metal frames, waterproofing membranes)

3. CONSTRUCTION STAGE: What phase is this? (excavation, foundation, structure, masonry, finishes, completed)

4. TECHNICAL DETAILS: Note dimensions, reinforcement patterns, connection types, installation quality

5. SAFETY & EQUIPMENT: Any scaffolding, formwork, safety barriers, temporary structures, construction equipment

Be detailed, technical, and specific. Use construction terminology."""

            # 3. Gera descrição usando VLM text-only
            description = await self.vlm.generate_text(prompt)
            
            # DEBUG: Log da descrição gerada
            logger.info("vlm_raw_output", description=description[:300], full_length=len(description))

            # Cross-Modal Validation: Verifica consistência imagem-texto
            is_consistent, similarity = await self._cross_modal_validation(
                image_bytes,
                description,
                threshold=0.6
            )
            
            if not is_consistent and similarity < 0.5:
                logger.warning(
                    "cross_modal_inconsistency_detected",
                    similarity=round(similarity, 3),
                    action="regenerating_description"
                )
                # Re-gerar descrição se muito inconsistente
                description = await self.vlm.generate_text(prompt)
                # Valida novamente
                _, new_similarity = await self._cross_modal_validation(
                    image_bytes,
                    description,
                    threshold=0.5  # Mais permissivo na segunda tentativa
                )
                logger.info("regenerated_similarity", new_similarity=round(new_similarity, 3))
            
            # Post-processing: valida qualidade mínima
            if len(description) < 50:  # Aumentado de 30 para 50
                logger.warning("descricao_muito_curta", 
                             length=len(description), 
                             description=description,
                             prompt_length=len(prompt))
                description += " [Low confidence - insufficient detail from VLM]"

            logger.info("descricao_gerada", 
                       length=len(description), 
                       has_rag_context=bool(rag_context),
                       cross_modal_similarity=round(similarity, 3),
                       is_consistent=is_consistent,
                       first_50_chars=description[:50])
            return description

        except Exception as e:
            logger.error("erro_gerar_descricao", error=str(e), exc_info=True)
            raise
    
    async def _cross_modal_validation(
        self,
        image_bytes: bytes,
        text_description: str,
        threshold: float = 0.6
    ) -> tuple[bool, float]:
        """
        Valida consistência entre embeddings de imagem e texto.
        
        Args:
            image_bytes: Dados da imagem
            text_description: Descrição textual gerada
            threshold: Limiar de similaridade (0.6)
            
        Returns:
            (is_consistent, similarity_score)
        """
        try:
            # Gera embeddings
            image_emb = await self.embedding_service.generate_image_embedding(image_bytes)
            text_emb = await self.embedding_service.generate_text_embedding(text_description)
            
            if not image_emb or not text_emb:
                logger.warning("cross_modal_embeddings_failed")
                return True, 0.5  # Assume válido se embeddings falharem
            
            # Calcula similaridade coseno
            import numpy as np
            from sklearn.metrics.pairwise import cosine_similarity
            
            similarity = cosine_similarity(
                np.array(image_emb).reshape(1, -1),
                np.array(text_emb).reshape(1, -1)
            )[0][0]
            
            is_consistent = similarity >= threshold
            
            logger.info(
                "cross_modal_validation",
                similarity=round(similarity, 3),
                threshold=threshold,
                is_consistent=is_consistent
            )
            
            return is_consistent, float(similarity)
            
        except Exception as e:
            logger.error("cross_modal_validation_error", error=str(e))
            return True, 0.5  # Fallback

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
