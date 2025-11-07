"""Serviço para matching de elementos BIM usando fuzzy matching."""

import structlog
from rapidfuzz import fuzz, process

from app.core.settings import get_settings
from app.schemas.bim import DetectedElement, ProgressStatus

logger = structlog.get_logger(__name__)


class ElementMatcher:
    """Serviço responsável por matching de elementos BIM."""

    # Palavras-chave expandidas por tipo de elemento
    ELEMENT_KEYWORDS = {
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

    async def compare_with_bim_model(
        self, image_description: str, project_data: dict, target_element_ids: list[str] | None = None
    ) -> dict:
        """
        Compara descrição da imagem com elementos do modelo BIM usando fuzzy matching.

        Args:
            image_description: Descrição textual da imagem
            project_data: Dados do projeto BIM
            target_element_ids: IDs específicos para análise

        Returns:
            Dicionário com elementos detectados
        """
        try:
            settings = get_settings()
            elements = project_data.get("elements", [])
            detected_elements = []

            description_lower = image_description.lower()

            for element in elements:
                if target_element_ids and element["element_id"] not in target_element_ids:
                    continue

                element_type = element["element_type"].lower()
                element_name = element.get("name", "").lower()

                is_detected = False
                confidence = 0.0
                match_method = "none"

                # Tenta match exato primeiro
                for type_key, keywords in self.ELEMENT_KEYWORDS.items():
                    if type_key in element_type:
                        for keyword in keywords:
                            if keyword in description_lower:
                                is_detected = True
                                confidence = 0.85
                                match_method = "exact"
                                break

                # Se não encontrou, tenta fuzzy matching
                if not is_detected:
                    for type_key, keywords in self.ELEMENT_KEYWORDS.items():
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
        """
        Determina o status de um elemento baseado na descrição.

        Args:
            element: Dados do elemento
            description: Descrição textual

        Returns:
            Status do elemento
        """
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

    def merge_detection_results(self, vector_results: list[dict], keyword_results: list[dict]) -> list[dict]:
        """
        Combina resultados de busca vetorial e keyword.
        Prioriza busca vetorial, usa keywords como fallback.

        Args:
            vector_results: Resultados da busca vetorial
            keyword_results: Resultados do matching por keywords

        Returns:
            Lista consolidada de elementos detectados
        """
        merged = {}

        # Adiciona resultados vetoriais (prioridade)
        for result in vector_results:
            element_id = result.get("element_id")
            if element_id:
                merged[element_id] = result

        # Adiciona resultados de keywords apenas se não existirem
        for result in keyword_results:
            element_id = result.get("element_id")
            if element_id and element_id not in merged:
                merged[element_id] = result

        return list(merged.values())
