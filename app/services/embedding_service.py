import io
from typing import List, Optional

import numpy as np
from PIL import Image
from sentence_transformers import SentenceTransformer

from app.core.logger import logger
from app.core.settings import settings


class EmbeddingService:
    """Service for generating image embeddings using CLIP."""

    def __init__(self):
        self.model_name = settings.embedding_model_name
        self.cache_dir = settings.vlm_model_cache_dir
        self.device = settings.device

        logger.info("initializing_embedding_model", model=self.model_name, device=self.device)

        # Load CLIP model for embeddings
        self.model = SentenceTransformer(self.model_name, cache_folder=self.cache_dir)

        if self.device != "cpu":
            self.model = self.model.to(self.device)

        logger.info("embedding_model_loaded")

    async def generate_image_embedding(self, image_data: bytes) -> List[float]:
        """Generate embedding vector for an image."""
        try:
            # Load and preprocess image
            image = Image.open(io.BytesIO(image_data)).convert("RGB")

            # Resize if needed
            max_size = settings.max_image_size
            if max(image.size) > max_size:
                image.thumbnail((max_size, max_size), Image.Resampling.LANCZOS)

            # Generate embedding
            embedding = self.model.encode(image, convert_to_numpy=True)

            # Convert to list and normalize
            embedding_list = embedding.tolist()

            logger.info("image_embedding_generated", dimension=len(embedding_list))
            return embedding_list

        except Exception as e:
            logger.error("embedding_generation_error", error=str(e))
            return []

    async def generate_text_embedding(self, text: str) -> List[float]:
        """Generate embedding vector for text."""
        try:
            # Generate embedding
            embedding = self.model.encode(text, convert_to_numpy=True)
            embedding_list = embedding.tolist()

            logger.info("text_embedding_generated", dimension=len(embedding_list))
            return embedding_list

        except Exception as e:
            logger.error("text_embedding_error", error=str(e))
            return []

    async def generate_multimodal_embedding(self, image_data: bytes, text: str) -> List[float]:
        """Generate combined embedding for image and text."""
        try:
            # Generate both embeddings
            image_embedding = await self.generate_image_embedding(image_data)
            text_embedding = await self.generate_text_embedding(text)

            if not image_embedding or not text_embedding:
                return image_embedding or text_embedding

            # Average the embeddings
            image_array = np.array(image_embedding)
            text_array = np.array(text_embedding)
            combined = (image_array + text_array) / 2

            logger.info("multimodal_embedding_generated")
            return combined.tolist()

        except Exception as e:
            logger.error("multimodal_embedding_error", error=str(e))
            return []


# Singleton instance
_embedding_service: Optional[EmbeddingService] = None


def get_embedding_service() -> EmbeddingService:
    """Get or create embedding service singleton."""
    global _embedding_service
    if _embedding_service is None:
        _embedding_service = EmbeddingService()
    return _embedding_service
