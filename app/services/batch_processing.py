"""
Serviço de processamento em lote para múltiplas imagens.
Análise paralela otimizada.
"""

import asyncio

import structlog

logger = structlog.get_logger(__name__)


class BatchProcessingService:
    """Serviço para processar múltiplas análises em paralelo."""

    def __init__(self, max_concurrent: int = 3):
        self.max_concurrent = max_concurrent
        self.semaphore = asyncio.Semaphore(max_concurrent)

    async def analyze_images_batch(
        self,
        images: list[tuple[bytes, str]],
        project_data: dict,
        bim_service,
        context: str | None = None,
    ) -> list[dict]:
        """Analisa múltiplas imagens em paralelo."""
        try:
            logger.info("batch_processing_iniciado", total_images=len(images))

            tasks = [
                self._analyze_single_with_semaphore(img_bytes, filename, project_data, bim_service, context)
                for img_bytes, filename in images
            ]

            results = await asyncio.gather(*tasks, return_exceptions=True)

            processed_results = []
            for i, result in enumerate(results):
                if isinstance(result, Exception):
                    processed_results.append({"filename": images[i][1], "error": str(result), "success": False})
                else:
                    processed_results.append({**result, "success": True})

            return processed_results

        except Exception as e:
            logger.error("erro_batch_processing", error=str(e))
            raise

    async def _analyze_single_with_semaphore(
        self, image_bytes: bytes, filename: str, project_data: dict, bim_service, context: str | None = None
    ) -> dict:
        """Analisa uma única imagem com controle de concorrência."""
        async with self.semaphore:
            result = await bim_service.analyze_construction_image(
                image_bytes=image_bytes, project_data=project_data, context=context
            )
            return {"filename": filename, **result}