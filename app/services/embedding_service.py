import gc
import io
import torch
import structlog
import numpy as np

from typing import List
from PIL import Image

from transformers import AutoProcessor, AutoModel
from sklearn.decomposition import PCA

logger = structlog.get_logger(__name__)

# Dimensão nativa do SigLIP
TARGET_DIM = 1152


class EmbeddingService:
    """
    Embedding Service usando:
      - SigLIP → texto e imagem (mesmo espaço)
    Dimensão padrão: 1152D (com PCA opcional).
    """

    def __init__(self, use_pca: bool = False):
        gc.collect()
        logger.info("loading_new_embedding_service")

        # ----------------------------
        # MODEL: SigLIP (transformers)
        # ----------------------------
        logger.info("loading_siglip")
        self.siglip_name = "google/siglip2-large-patch16-256"

        # Processor + model
        self.siglip_processor = AutoProcessor.from_pretrained(self.siglip_name)
        self.siglip_model = AutoModel.from_pretrained(self.siglip_name)
        self.siglip_model.eval()

        # PCA (opcional)
        self.use_pca = use_pca
        self.pca = None

        if use_pca:
            logger.info("initializing_pca_target_dim", dim=TARGET_DIM)

    # ==============================================================
    # HELPERS
    # ==============================================================

    def _norm(self, v: np.ndarray) -> List[float]:
        """Normalização L2."""
        if v is None or np.isnan(v).any():
            return []
        v = v / (np.linalg.norm(v) + 1e-12)
        return v.tolist()

    def _apply_pca(self, vec: np.ndarray) -> np.ndarray:
        """Redução PCA opcional."""
        if not self.use_pca:
            return vec
        if self.pca is None:
            raise RuntimeError("PCA not fitted yet — call fit_pca().")
        return self.pca.transform([vec])[0]

    # ==============================================================
    # PUBLIC METHODS
    # ==============================================================

    async def fit_pca(self, samples: List[np.ndarray]):
        """
        Ajusta PCA usando embeddings brutos (texto + imagem).
        """
        logger.info("fitting_pca", samples=len(samples))

        self.pca = PCA(n_components=TARGET_DIM)
        self.pca.fit(samples)

        logger.info("pca_fit_complete")

    # --------------------------------------------------------------
    async def generate_text_embedding(self, text: str) -> List[float]:
        try:
            # --- SIGLIP TEXT LIMIT FIX ---
            # SigLIP suporta no máximo 64 tokens → limitar a ~200 chars
            safe_text = text[:200]

            inputs = self.siglip_processor(
                text=[safe_text],
                return_tensors="pt",
                truncation=True,   # garante que nunca ultrapassa 64 tokens
            )

            with torch.no_grad():
                vec = self.siglip_model.get_text_features(**inputs)[0].numpy()  # 1152D

            # PCA opcional → reduz para 1024D
            if self.use_pca:
                vec = self._apply_pca(vec)

            return self._norm(vec)

        except Exception as e:
            logger.error("siglip_text_embedding_error", error=str(e))
            return []


    # --------------------------------------------------------------
    async def generate_image_embedding(self, image_bytes: bytes) -> List[float]:
        """SigLIP imagem → 1152D"""
        try:
            img = Image.open(io.BytesIO(image_bytes)).convert("RGB")
            inputs = self.siglip_processor(images=img, return_tensors="pt")

            with torch.no_grad():
                vec = self.siglip_model.get_image_features(**inputs)[0].numpy()

            if self.use_pca:
                vec = self._apply_pca(vec)

            return self._norm(vec)

        except Exception as e:
            logger.error("siglip_image_embedding_error", error=str(e))
            return []

    # --------------------------------------------------------------
    async def generate_multimodal_embedding(self, image_bytes: bytes, text: str) -> List[float]:
        """Combinação simples texto + imagem → mesma dimensão"""
        try:
            emb_text = np.array(await self.generate_text_embedding(text))
            emb_img = np.array(await self.generate_image_embedding(image_bytes))

            if emb_text.size == 0 or emb_img.size == 0:
                return []

            fused = (emb_text + emb_img) / 2.0
            return self._norm(fused)

        except Exception as e:
            logger.error("multimodal_embedding_error", error=str(e))
            return []


# Singleton
_embedding_service: EmbeddingService | None = None


def get_embedding_service() -> EmbeddingService:
    global _embedding_service
    if _embedding_service is None:
        _embedding_service = EmbeddingService(use_pca=False)
    return _embedding_service
