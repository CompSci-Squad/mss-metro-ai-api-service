#!/usr/bin/env python3
"""Quantização INT8 do BLIP-2 via bitsandbytes (CPU-friendly)."""

from transformers import Blip2ForConditionalGeneration, BitsAndBytesConfig
from pathlib import Path

def main():
    print("=" * 60)
    print("⚙️ QUANTIZAÇÃO INT8 - BLIP-2 (bitsandbytes)")
    print("=" * 60)

    model_dir = "./models/blip2-flan-t5-xl"
    save_dir = Path("./models/blip2-flan-t5-xl-int8")
    save_dir.mkdir(parents=True, exist_ok=True)

    print("🧠 Aplicando quantização INT8 (bitsandbytes)...")

    bnb_config = BitsAndBytesConfig(
        load_in_8bit=True,
        llm_int8_threshold=6.0,
        llm_int8_enable_fp32_cpu_offload=True
    )

    model = Blip2ForConditionalGeneration.from_pretrained(
        model_dir,
        quantization_config=bnb_config,
        device_map="cpu"
    )

    print("💾 Salvando modelo quantizado...")
    model.save_pretrained(save_dir)

    print("✅ Modelo quantizado salvo em:", save_dir)
    print("=" * 60)

if __name__ == "__main__":
    main()
