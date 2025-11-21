"""Serviço VLM simplificado usando MiniCPM-V-4.5-GGUF (INT8, CPU)."""

import os
import time
from pathlib import Path

from huggingface_hub import hf_hub_download
from llama_cpp import Llama

from app.core.logger import logger


def log_memory_usage(stage: str):
    """Log de uso de memória para debug."""
    try:
        import psutil
        process = psutil.Process()
        mem_info = process.memory_info()
        logger.info(
            f"memory_usage_{stage}",
            rss_gb=round(mem_info.rss / 1024**3, 2),
            available_gb=round(psutil.virtual_memory().available / 1024**3, 2)
        )
    except ImportError:
        pass


def get_model_path() -> str:
    """
    Garante que o modelo GGUF está disponível localmente.

    Returns:
        Caminho completo para o arquivo .gguf
    """
    cache_dir = Path("./models/minicpm-v4_5-int8")
    cache_dir.mkdir(parents=True, exist_ok=True)

    model_filename = "MiniCPM-V-4_5-Q8_0.gguf"  # Nome exato do HuggingFace
    local_file = cache_dir / model_filename

    if not local_file.exists():
        logger.info(
            "downloading_model",
            repo="openbmb/MiniCPM-V-4_5-gguf",
            filename=model_filename,
            cache_dir=str(cache_dir)
        )

        try:
            hf_hub_download(
                repo_id="openbmb/MiniCPM-V-4_5-gguf",
                filename=model_filename,
                local_dir=str(cache_dir),
                local_dir_use_symlinks=False
            )
            logger.info("model_download_complete", path=str(local_file))
        except Exception as e:
            logger.error("model_download_failed", error=str(e), exc_info=True)
            raise
    else:
        logger.info("model_found_in_cache", path=str(local_file))

    return str(local_file)


class VLMService:
    """
    Serviço simplificado de inferência textual com MiniCPM-V-4.5-GGUF.

    Características:
    - INT8 quantizado (GGUF nativo)
    - 100% CPU
    - Cache local permanente
    - Sem torch/transformers
    - Interface simplificada (texto → texto)
    """

    def __init__(self):
        """Inicializa o serviço VLM com modelo GGUF quantizado."""
        logger.info("initializing_vlm_service_gguf")
        log_memory_usage("before_model_load")

        # Obtém caminho do modelo (baixa se necessário)
        model_path = get_model_path()

        # Determina threads disponíveis
        n_threads = os.cpu_count() or 4
        
        logger.info(
            "loading_gguf_model",
            model_path=model_path,
            model_type="minicpm",
            gpu_layers=0,
            cpu_threads=n_threads,
            use_mmap=True
        )

        start_time = time.time()

        try:
            # Carrega modelo GGUF com llama-cpp-python (otimizado para CPU)
            self.model = Llama(
                model_path=model_path,
                n_ctx=8192,  # Context length (aumentado para prompts longos)
                n_threads=os.cpu_count() or 4,  # Usa todos os cores disponíveis
                n_batch=512,  # Batch size para processamento eficiente
                n_gpu_layers=0,  # Força CPU (0 = sem GPU)
                use_mmap=True,  # Leitura direta do arquivo (economiza RAM)
                use_mlock=False,  # Não trava em memória física
                embedding=False,  # Não gera embeddings
                logits_all=False,  # Não retorna todos os logits
                verbose=False
            )

            load_time = time.time() - start_time

            logger.info(
                "gguf_model_loaded",
                load_time_seconds=round(load_time, 2),
                model_type="minicpm-v-4.5-gguf-int8",
                backend="llama-cpp-python"
            )

            log_memory_usage("after_model_load")

        except Exception as e:
            logger.error("model_load_failed", error=str(e), exc_info=True)
            raise

    async def generate_text(self, prompt: str, max_tokens: int = 512) -> str:
        """
        Gera resposta textual para um prompt técnico.

        Args:
            prompt: Prompt de entrada
            max_tokens: Número máximo de tokens a gerar

        Returns:
            Texto gerado pelo modelo
        """
        try:
            start_time = time.time()

            logger.info(
                "generating_text",
                prompt_length=len(prompt),
                max_tokens=max_tokens
            )

            # Geração com llama-cpp-python (API create_completion)
            output = self.model.create_completion(
                prompt=prompt.strip(),
                max_tokens=max_tokens,
                temperature=0.6,  # Temperatura baixa para respostas mais precisas
                top_p=0.9,
                repeat_penalty=1.1,
                stop=["</s>", "###", "User:", "\n\n\n"]  # Stop tokens
            )

            generation_time = time.time() - start_time

            # Extrai texto da resposta
            if not output or "choices" not in output or len(output["choices"]) == 0:
                logger.warning("empty_response_from_model")
                return "[Erro: resposta vazia do modelo]"

            response_text = output["choices"][0]["text"]
            result = response_text.strip()

            logger.info(
                "text_generated",
                response_length=len(result),
                generation_time_seconds=round(generation_time, 2)
            )

            return result

        except Exception as e:
            logger.error("text_generation_error", error=str(e), exc_info=True)
            return f"[Erro na geração: {str(e)}]"

    async def generate_caption(self, image_data: bytes, prompt: str = "") -> str:
        """
        Método de compatibilidade para generate_caption.
        
        NOTA: Este modelo GGUF é text-only. Para análise de imagem,
        use embedding_service para extrair contexto e injete no prompt.
        
        Args:
            image_data: Dados da imagem (ignorados)
            prompt: Prompt textual
            
        Returns:
            Resposta textual
        """
        logger.warning(
            "generate_caption_called_on_text_only_model",
            message="Use embedding_service + generate_text para análise de imagem"
        )

        # Se tem prompt, usa ele
        if prompt:
            return await self.generate_text(prompt)

        # Se não tem prompt, retorna mensagem
        return "[Esta versão do modelo aceita apenas texto. Use embedding_service para extrair contexto da imagem]"

    async def answer_question(self, image_data: bytes, question: str) -> str:
        """
        Método de compatibilidade para answer_question.
        Redireciona para generate_text.
        """
        return await self.generate_text(question)


# Singleton instance
_vlm_service: VLMService | None = None


def get_vlm_service() -> VLMService:
    """Get or create VLM service singleton."""
    global _vlm_service
    if _vlm_service is None:
        _vlm_service = VLMService()
    return _vlm_service
