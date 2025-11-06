#!/usr/bin/env python3

import argparse
import gc
import sys
import warnings
from pathlib import Path

import torch
from transformers import Blip2ForConditionalGeneration

# Suprime warning de deprecation do quantize_dynamic (será migrado no futuro)
warnings.filterwarnings("ignore", category=DeprecationWarning, module="torch")


def quantize_blip2(
    model_name: str = "Salesforce/blip2-opt-2.7b",
    cache_dir: str = "./models",
    output_file: str = "blip2-int8-dynamic.pt",
):
    """Quantiza modelo BLIP2 e salva."""

    print(f"Quantizando modelo: {model_name}")
    print(f"Cache dir: {cache_dir}")

    print("Carregando modelo FP32...")
    base_model = Blip2ForConditionalGeneration.from_pretrained(
        model_name,
        cache_dir=cache_dir,
        low_cpu_mem_usage=True,
        torch_dtype=torch.float16,
    )
    base_model.eval()
    print("Modelo carregado!")

    print("Aplicando quantização INT8...")
    quantized_model = torch.quantization.quantize_dynamic(base_model, {torch.nn.Linear}, dtype=torch.qint8)
    print("Quantização completa!")

    del base_model
    gc.collect()

    output_path = Path(cache_dir) / output_file
    output_path.parent.mkdir(parents=True, exist_ok=True)

    print(f"Salvando modelo quantizado: {output_path}")
    torch.save(quantized_model, str(output_path))

    size_mb = output_path.stat().st_size / 1024 / 1024
    print(f"Modelo salvo! Tamanho: {size_mb:.1f} MB")

    print("Testando carregamento...")
    test_model = torch.load(str(output_path), map_location="cpu", weights_only=False)
    print("Modelo carrega corretamente!")
    del test_model  # Libera memória do teste

    print(f"Sucesso! Modelo quantizado pronto em: {output_path}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Quantiza BLIP2 para INT8")
    parser.add_argument("--model", default="Salesforce/blip2-opt-2.7b", help="Nome do modelo HuggingFace")
    parser.add_argument("--cache-dir", default="./models", help="Diretório de cache")
    parser.add_argument("--output", default="blip2-int8-dynamic.pt", help="Nome do arquivo de saída")

    args = parser.parse_args()

    try:
        quantize_blip2(args.model, args.cache_dir, args.output)
    except Exception as e:
        print(f"❌ Erro: {e}", file=sys.stderr)
        import traceback

        traceback.print_exc()
        sys.exit(1)
