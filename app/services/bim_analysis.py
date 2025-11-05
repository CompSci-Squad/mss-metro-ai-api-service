"""Serviço de análise BIM com VI-RAG."""

import time

import structlog
from rapidfuzz import fuzz, process

from app.core.settings import get_settings
from app.schemas.bim import DetectedElement, ProgressStatus
from app.services.embedding_service import EmbeddingService
from app.services.vlm_service import VLMService

logger = structlog.get_logger(__name__)


class BIMAnalysisService:
    def __init__(self, vlm_service: VLMService, embedding_service: EmbeddingService):
        self.vlm = vlm_service
        self.embedding_service = embedding_service

    async def _generate_image_embedding(self, image_bytes: bytes) -> list[float]:
        """Gera embedding da imagem usando CLIP."""
        try:
            from PIL import Image
            import io

            image = Image.open(io.BytesIO(image_bytes))
            embedding = await self.embedding_service.generate_image_embedding(image_bytes)

            logger.info("image_embedding_gerado", embedding_dim=len(embedding))
            return embedding

        except Exception as e:
            logger.error("erro_gerar_embedding_imagem", error=str(e))
            raise

    async def _fetch_rag_context(self, image_embedding: list[float], project_id: str, top_k: int = 10) -> dict:
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

            # 1. Gera descrição da imagem usando VLM
            description = await self._generate_image_description(image_bytes, context)

            # 2. Gera embedding da descrição
            description_embedding = await self.embedding_service.generate_embedding(description)

            # 3. Busca elementos similares usando OpenSearch (busca vetorial)
            vector_matches = await self._find_similar_elements_vector(
                project_data.get("project_id"),
                description_embedding,
                target_element_ids,
            )

            # 4. Compara descrição com modelo BIM (fallback)
            keyword_matches = await self._compare_with_bim_model(description, project_data, target_element_ids)

            # 5. Combina resultados (vetorial + keywords)
            detected_elements = self._merge_detection_results(vector_matches, keyword_matches["detected_elements"])

            # 6. Calcula métricas de progresso
            progress_metrics = self._calculate_progress_metrics(detected_elements, project_data.get("elements", []))

            # 7. Identifica alertas
            alerts = self._identify_alerts(detected_elements, project_data)

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

    async def _generate_image_description(self, image_bytes: bytes, context: str | None = None) -> str:
        """Gera descrição textual da imagem usando VLM."""
        try:
            prompt = """Analyze this construction site image in detail. Focus on:
            1. Structural elements visible (walls, columns, slabs, beams, foundations)
            2. Construction progress and completion status
            3. Materials and building techniques visible
            4. Any deviations, quality issues, or safety concerns
            5. Overall construction phase

            Provide a detailed technical description."""

            if context:
                prompt += f"\n\nAdditional context: {context}"

            # Usa VLMService existente
            description = await self.vlm_service.generate_caption(image_bytes, prompt)

            logger.info("descricao_gerada", length=len(description))
            return description

        except Exception as e:
            logger.error("erro_gerar_descricao", error=str(e))
            raise

    async def _compare_with_bim_model(
        self, image_description: str, project_data: dict, target_element_ids: list[str] | None = None
    ) -> dict:
        """Compara descrição da imagem com elementos do modelo BIM usando fuzzy matching."""
        try:
            settings = get_settings()
            elements = project_data.get("elements", [])
            detected_elements = []

            description_lower = image_description.lower()

            # Palavras-chave expandidas por tipo de elemento
            element_keywords = {
                "wall": ["wall", "parede", "alvenaria", "masonry", "muro", "divisa"],
                "slab": ["slab", "laje", "floor", "piso", "pavimento", "deck"],
                "column": ["column", "pilar", "coluna", "suporte", "apoio"],
                "beam": ["beam", "viga", "trave"],
                "foundation": ["foundation", "fundação", "footing", "pile", "sapata", "estaca", "radier"],
                "stair": ["stair", "escada", "stairs", "degrau", "rampa"],
                "roof": ["roof", "telhado", "cobertura", "telha"],
                "door": ["door", "porta", "acesso", "entrada"],
                "window": ["window", "janela", "abertura", "esquadria"],
            }

            for element in elements:
                if target_element_ids and element["element_id"] not in target_element_ids:
                    continue

                element_type = element["element_type"].lower()
                element_name = element.get("name", "").lower()

                is_detected = False
                confidence = 0.0
                match_method = "none"

                # Tenta match exato primeiro
                for type_key, keywords in element_keywords.items():
                    if type_key in element_type:
                        for keyword in keywords:
                            if keyword in description_lower:
                                is_detected = True
                                confidence = 0.85
                                match_method = "exact"
                                break

                # Se não encontrou, tenta fuzzy matching
                if not is_detected:
                    for type_key, keywords in element_keywords.items():
                        if type_key in element_type:
                            # Fuzzy match nas keywords
                            best_match = process.extractOne(
                                element_name or element_type, keywords, scorer=fuzz.partial_ratio
                            )

                            if best_match and best_match[1] >= settings.fuzzy_match_threshold:
                                # Verifica se o melhor match está na descrição
                                desc_match = fuzz.partial_ratio(best_match[0], description_lower)
                                if desc_match >= settings.fuzzy_match_threshold:
                                    is_detected = True
                                    confidence = min(desc_match / 100.0, 0.90)
                                    match_method = "fuzzy"
                                    break

                if is_detected:
                    status = self._determine_element_status(element, description_lower)

                    detected_element = DetectedElement(
                        element_id=element["element_id"],
                        element_type=element["element_type"],
                        confidence=round(confidence, 3),
                        status=status,
                        description=f"{element['element_type']} detectado ({match_method} match)",
                        deviation=None,
                    )

                    detected_elements.append(detected_element.model_dump())

                    logger.debug(
                        "elemento_detectado",
                        element_id=element["element_id"],
                        type=element["element_type"],
                        confidence=confidence,
                        method=match_method,
                    )

            return {"detected_elements": detected_elements}

        except Exception as e:
            logger.error("erro_comparar_bim", error=str(e))
            raise

    def _determine_element_status(self, element: dict, description: str) -> ProgressStatus:
        """Determina o status de um elemento baseado na descrição."""
        completed_keywords = ["completed", "finished", "concluído", "finalizado", "pronto"]
        in_progress_keywords = ["progress", "construction", "building", "em andamento", "construção"]
        not_started_keywords = ["not started", "missing", "absent", "não iniciado", "ausente"]

        if any(keyword in description for keyword in completed_keywords):
            return ProgressStatus.COMPLETED

        if any(keyword in description for keyword in in_progress_keywords):
            return ProgressStatus.IN_PROGRESS

        if any(keyword in description for keyword in not_started_keywords):
            return ProgressStatus.NOT_STARTED

        return ProgressStatus.IN_PROGRESS

    def _calculate_progress_metrics(self, detected_elements: list[dict], all_elements: list[dict]) -> dict:
        """Calcula métricas de progresso."""
        if not all_elements:
            return {"overall_progress": 0.0}

        total_elements = len(all_elements)
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

    def _identify_alerts(self, detected_elements: list[dict], project_data: dict) -> list[str]:
        """Identifica alertas baseado na análise."""
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

    async def _find_similar_elements_vector(
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

    def _merge_detection_results(self, vector_results: list[dict], keyword_results: list[dict]) -> list[dict]:
        """
        Combina resultados de busca vetorial e keyword.
        Prioriza busca vetorial, usa keywords como fallback.

        Args:
            vector_results: Resultados da busca vetorial
            keyword_results: Resultados da busca por palavras-chave

        Returns:
            Lista combinada e deduplicada
        """
        merged = {}

        # Adiciona resultados vetoriais (prioridade)
        for result in vector_results:
            element_id = result.get("element_id")
            merged[element_id] = result

        # Adiciona keywords apenas se não existir
        for result in keyword_results:
            element_id = result.get("element_id")
            if element_id not in merged:
                merged[element_id] = result

        return list(merged.values())

    async def _get_previous_analysis(self, project_id: str) -> dict | None:
        """
        Busca a análise mais recente do projeto para comparação.

        Args:
            project_id: ID do projeto

        Returns:
            Dados da análise anterior ou None
        """
        try:
            from app.models.dynamodb import ConstructionAnalysisModel

            # Busca análises ordenadas por data (mais recente primeiro)
            analyses = list(
                ConstructionAnalysisModel.project_id_index.query(
                    project_id,
                    scan_index_forward=False,  # Ordem decrescente
                    limit=1,
                )
            )

            if not analyses:
                logger.info("nenhuma_analise_anterior", project_id=project_id)
                return None

            previous = analyses[0]

            result = {
                "analysis_id": previous.analysis_id,
                "analyzed_at": previous.analyzed_at,
                "overall_progress": previous.overall_progress,
                "detected_elements": previous.detected_elements,
                "summary": previous.summary,
            }

            logger.info("analise_anterior_encontrada", analysis_id=previous.analysis_id)
            return result

        except Exception as e:
            logger.warning("erro_buscar_analise_anterior", error=str(e))
            return None

    async def _compare_with_previous_analysis(
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
            from app.schemas.bim import ProgressStatus

            previous_elements = previous_analysis.get("detected_elements", [])
            previous_progress = previous_analysis.get("overall_progress", 0.0)

            # Calcula progresso atual
            current_progress = self._calculate_overall_progress(current_elements)
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
