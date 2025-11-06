import io
from pathlib import Path
from typing import Optional

import numpy as np
import torch
from PIL import Image
from transformers import AutoProcessor, Blip2ForConditionalGeneration, Blip2Processor

from app.core.logger import logger
from app.core.settings import settings


class VLMService:
    """Vision-Language Model service for image understanding and captioning."""

    def __init__(self):
        self.device = settings.device
        self.model_name = settings.vlm_model_name
        self.cache_dir = settings.vlm_model_cache_dir
        self.use_quantization = settings.use_quantization

        logger.info(
            "initializing_vlm_model",
            model=self.model_name,
            device=self.device,
            quantization=self.use_quantization,
            intel_optimum=INTEL_OPTIMUM_AVAILABLE
        )

        # Load processor
        self.processor = AutoProcessor.from_pretrained(self.model_name, cache_dir=self.cache_dir)

        # Load model with quantization strategy
        if self.use_quantization and self.device == "cpu":
            # PyTorch Dynamic INT8 Quantization
            logger.info("using_pytorch_int8_quantization")
            
            quantized_model_path = Path(self.cache_dir) / "blip2-int8-dynamic"
            
            # Verifica se modelo quantizado já existe em cache
            if quantized_model_path.exists():
                logger.info("loading_cached_quantized_model", path=str(quantized_model_path))
                try:
                    self.model = Blip2ForConditionalGeneration.from_pretrained(quantized_model_path)
                    logger.info("quantized_model_loaded_from_cache")
                except Exception as e:
                    logger.warning("failed_to_load_cached_model", error=str(e))
                    # Se falhar, recria
                    quantized_model_path = None
            
            if not quantized_model_path or not quantized_model_path.exists():
                # Carrega modelo original em FP32
                logger.info("loading_fp32_model_for_quantization")
                base_model = Blip2ForConditionalGeneration.from_pretrained(
                    self.model_name,
                    cache_dir=self.cache_dir
                )
                base_model.eval()
                
                # Aplica quantização dinâmica INT8
                logger.info("applying_dynamic_int8_quantization")
                self.model = torch.quantization.quantize_dynamic(
                    base_model,
                    {torch.nn.Linear},  # Quantiza apenas camadas lineares
                    dtype=torch.qint8   # INT8
                )
                
                # Salva modelo quantizado para cache
                logger.info("saving_quantized_model", path=str(quantized_model_path))
                quantized_model_path.mkdir(parents=True, exist_ok=True)
                self.model.save_pretrained(str(quantized_model_path))
                logger.info("quantization_complete")
            
            self.model = self.model.to(self.device)
            logger.info("int8_quantized_model_ready")
            
        elif self.use_quantization:
            # GPU ou outro device: usa float16
            logger.info("using_float16_quantization")
            self.model = Blip2ForConditionalGeneration.from_pretrained(
                self.model_name,
                cache_dir=self.cache_dir,
                torch_dtype=torch.float16,
            )
            self.model = self.model.to(self.device)
        else:
            # Standard loading without quantization
            logger.info("loading_model_without_quantization")
            self.model = Blip2ForConditionalGeneration.from_pretrained(
                self.model_name,
                cache_dir=self.cache_dir
            )
            self.model = self.model.to(self.device)

        self.model.eval()
        logger.info("vlm_model_ready")
        logger.info("vlm_model_loaded", quantized=self.use_quantization)

    async def generate_caption(self, image_data: bytes, prompt: str = "") -> str:
        """Generate a caption for an image."""
        try:
            # Load image
            image = Image.open(io.BytesIO(image_data)).convert("RGB")

            # Preprocess
            if prompt:
                inputs = self.processor(image, text=prompt, return_tensors="pt")
            else:
                inputs = self.processor(image, return_tensors="pt")

            # Move inputs to device
            if self.device != "cpu":
                inputs = {k: v.to(self.device) for k, v in inputs.items()}

            # Generate
            with torch.no_grad():
                generated_ids = self.model.generate(**inputs, max_length=50, num_beams=5)

            # Decode
            caption = self.processor.batch_decode(generated_ids, skip_special_tokens=True)[0].strip()

            logger.info("caption_generated", caption_length=len(caption))
            return caption

        except Exception as e:
            logger.error("caption_generation_error", error=str(e))
            return ""

    async def answer_question(self, image_data: bytes, question: str) -> str:
        """Answer a question about an image using VLM."""
        try:
            # Load image
            image = Image.open(io.BytesIO(image_data)).convert("RGB")

            # Create prompt
            prompt = f"Question: {question} Answer:"

            # Preprocess
            inputs = self.processor(image, text=prompt, return_tensors="pt")

            # Move inputs to device
            if self.device != "cpu":
                inputs = {k: v.to(self.device) for k, v in inputs.items()}

            # Generate
            with torch.no_grad():
                generated_ids = self.model.generate(**inputs, max_length=100, num_beams=5)

            # Decode
            answer = self.processor.batch_decode(generated_ids, skip_special_tokens=True)[0].strip()

            logger.info("question_answered", question_length=len(question), answer_length=len(answer))
            return answer

        except Exception as e:
            logger.error("question_answering_error", error=str(e))
            return ""

    async def compare_images(self, image_1_data: bytes, image_2_data: bytes) -> dict:
        """Compare two images and describe differences."""
        try:
            # Generate captions for both images
            caption_1 = await self.generate_caption(image_1_data)
            caption_2 = await self.generate_caption(image_2_data)

            # Generate comparison prompt
            comparison_prompt = "Describe the differences between these images:"

            # For now, return basic comparison based on captions
            # In production, could use more sophisticated comparison
            comparison = {
                "image_1_description": caption_1,
                "image_2_description": caption_2,
                "summary": f"Image 1: {caption_1}. Image 2: {caption_2}.",
            }

            logger.info("images_compared")
            return comparison

        except Exception as e:
            logger.error("image_comparison_error", error=str(e))
            return {
                "image_1_description": "",
                "image_2_description": "",
                "summary": "Error comparing images",
            }


# Singleton instance
_vlm_service: Optional[VLMService] = None


def get_vlm_service() -> VLMService:
    """Get or create VLM service singleton."""
    global _vlm_service
    if _vlm_service is None:
        _vlm_service = VLMService()
    return _vlm_service
