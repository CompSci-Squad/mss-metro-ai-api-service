"""Serviço de busca vetorial RAG usando OpenSearch."""

import structlog

from app.core.cache_decorator import cache_result
from app.schemas.bim import DetectedElement, ProgressStatus

logger = structlog.get_logger(__name__)


class RAGSearchService:
    """Serviço responsável por buscas vetoriais no OpenSearch."""

    @cache_result(ttl=1800, key_prefix="rag_context")
    async def fetch_rag_context(self, image_embedding: list[float], project_id: str, top_k: int = 10) -> dict:
        """
        Busca contexto RAG usando embedding da imagem.
        Resultado cacheado por 30 minutos.

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
            search = BIMElementEmbedding.search_by_vector(
                query_embedding=image_embedding, size=top_k, project_id=project_id
            )

            results = search.execute()

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

            for hit in results:
                # Score de similaridade (0-1)
                confidence = hit.meta.score if hasattr(hit.meta, "score") else 0.5

                # Filtra por IDs se especificado
                if target_ids and hit.element_id not in target_ids:
                    continue

                # Determina status baseado na confiança
                if confidence > 0.8:
                    status = ProgressStatus.COMPLETED
                elif confidence > 0.5:
                    status = ProgressStatus.IN_PROGRESS
                else:
                    status = ProgressStatus.NOT_STARTED

                detected_element = DetectedElement(
                    element_id=hit.element_id,
                    element_type=hit.element_type,
                    confidence=round(confidence, 3),
                    status=status,
                    description=hit.description,
                    deviation=None,
                )

                detected.append(detected_element.model_dump())

            logger.info("busca_vetorial_concluida", detected=len(detected))
            return detected

        except Exception as e:
            logger.warning("erro_busca_vetorial", error=str(e))
            return []
