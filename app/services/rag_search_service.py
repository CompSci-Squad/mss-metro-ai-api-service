"""Serviço de busca vetorial RAG usando OpenSearch."""

import structlog

from app.schemas.bim import DetectedElement, ProgressStatus

logger = structlog.get_logger(__name__)


class RAGSearchService:
    """Serviço responsável por buscas vetoriais no OpenSearch."""

    async def fetch_rag_context(self, image_embedding: list[float], project_id: str, top_k: int = 150) -> dict:
        """
        Busca contexto RAG usando embedding da imagem.

        Args:
            image_embedding: Vetor embedding da imagem
            project_id: ID do projeto
            top_k: Número de elementos a retornar

        Returns:
            Dicionário com elementos encontrados e total
        """
        try:
            from app.models.opensearch import BIMElementEmbedding

            # Busca elementos similares usando KNN
            # search_by_vector já retorna lista de resultados (não precisa .execute())
            results = BIMElementEmbedding.search_by_vector(
                query_embedding=image_embedding, size=top_k, project_id=project_id
            )

            # Extrai elementos relevantes
            context_elements = []
            for hit in results:
                context_elements.append(
                    {
                        "element_id": hit.element_id,
                        "element_type": hit.element_type,
                        "description": hit.description,
                        "element_name": hit.element_name or "",
                        "similarity_score": hit.meta.score if hasattr(hit.meta, "score") else None,
                    }
                )

            logger.info("rag_context_buscado", elements_found=len(context_elements))

            return {
                "elements": context_elements,
                "total_found": len(context_elements),
            }

        except Exception as e:
            logger.error("erro_buscar_rag_context", error=str(e))
            # Retorna contexto vazio em caso de erro
            return {"elements": [], "total_found": 0}

    async def find_similar_elements_vector(
        self, project_id: str, query_embedding: list[float], target_ids: list[str] | None = None
    ) -> list[dict]:
        """
        Busca elementos similares usando busca vetorial no OpenSearch.

        Args:
            project_id: ID do projeto
            query_embedding: Embedding da descrição da imagem
            target_ids: IDs específicos para filtrar

        Returns:
            Lista de elementos detectados com confiança
        """
        try:
            from app.models.opensearch import BIMElementEmbedding

            # Busca vetorial (KNN)
            results = BIMElementEmbedding.search_by_vector(
                query_embedding=query_embedding, size=20, project_id=project_id
            )

            detected = []
            
            # Coleta scores para normalização
            scores = [hit.meta.score for hit in results if hasattr(hit.meta, "score")]
            
            if scores:
                max_score = max(scores)
                min_score = min(scores)
                score_range = max_score - min_score
            else:
                max_score = 1.0
                min_score = 0.0
                score_range = 1.0

            for hit in results:
                # Normaliza score para 0-1
                raw_score = hit.meta.score if hasattr(hit.meta, "score") else 0.5
                
                # Calcula confidence
                if score_range > 0.01:
                    # Scores variados: normaliza no range
                    confidence = (raw_score - min_score) / score_range
                else:
                    # Scores similares: usa score diretamente (já está 0-1)
                    # KNN scores geralmente estão entre 0 e 1
                    confidence = min(raw_score, 1.0) if raw_score >= 0 else 0.5

                # Clamp para garantir range [0, 1]
                confidence = max(0.0, min(1.0, confidence))

                # Filtra por IDs se especificado
                if target_ids and hit.element_id not in target_ids:
                    continue

                # Determina status baseado na confiança normalizada
                if confidence > 0.7:
                    status = ProgressStatus.COMPLETED
                elif confidence > 0.4:
                    status = ProgressStatus.IN_PROGRESS
                else:
                    status = ProgressStatus.NOT_STARTED

                # Monta descrição no formato: "Nome (Tipo)"
                element_name = getattr(hit, 'element_name', None) or 'Sem nome'
                element_type = getattr(hit, 'element_type', 'Element')
                
                final_description = f"{element_name} ({element_type})"

                detected_element = DetectedElement(
                    element_id=hit.element_id,
                    element_type=hit.element_type,
                    confidence=round(confidence, 3),
                    status=status,
                    description=final_description,
                    deviation=None,
                )

                detected.append(detected_element.model_dump())

            logger.info("busca_vetorial_concluida", detected=len(detected))
            return detected

        except Exception as e:
            logger.warning("erro_busca_vetorial", error=str(e))
            return []
