"""
Serviço de processamento de imagens.
Compressão, normalização e otimização.
"""

import io

import structlog
from PIL import Image

logger = structlog.get_logger(__name__)


class ImageProcessingService:
    """Serviço para processar e otimizar imagens."""

    def __init__(
        self,
        max_width: int = 1920,
        max_height: int = 1920,
        quality: int = 85,
        format: str = "JPEG",
    ):
        self.max_width = max_width
        self.max_height = max_height
        self.quality = quality
        self.format = format

    async def compress_image(self, image_bytes: bytes) -> tuple[bytes, dict]:
        """Comprime e otimiza imagem."""
        try:
            original_size = len(image_bytes)
            img = Image.open(io.BytesIO(image_bytes))

            # Converte para RGB
            if img.mode in ("RGBA", "LA", "P"):
                background = Image.new("RGB", img.size, (255, 255, 255))
                if img.mode == "P":
                    img = img.convert("RGBA")
                background.paste(img, mask=img.split()[-1] if img.mode in ("RGBA", "LA") else None)
                img = background
            elif img.mode != "RGB":
                img = img.convert("RGB")

            original_width, original_height = img.size

            # Redimensiona se necessário
            if img.width > self.max_width or img.height > self.max_height:
                img.thumbnail((self.max_width, self.max_height), Image.Resampling.LANCZOS)

            # Comprime
            output = io.BytesIO()
            img.save(output, format=self.format, quality=self.quality, optimize=True, progressive=True)
            compressed_bytes = output.getvalue()

            compressed_size = len(compressed_bytes)
            compression_ratio = (1 - compressed_size / original_size) * 100

            metadata = {
                "original_size": original_size,
                "compressed_size": compressed_size,
                "compression_ratio": round(compression_ratio, 2),
                "original_dimensions": f"{original_width}x{original_height}",
                "final_dimensions": f"{img.width}x{img.height}",
                "format": self.format,
                "quality": self.quality,
            }

            logger.info("imagem_comprimida", ratio=f"{compression_ratio:.1f}%")
            return compressed_bytes, metadata

        except Exception as e:
            logger.error("erro_comprimir_imagem", error=str(e))
            return image_bytes, {"error": str(e)}