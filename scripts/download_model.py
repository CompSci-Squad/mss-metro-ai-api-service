#!/usr/bin/env python3
"""Download do MiniCPM-V 2.6 multimodal GGUF (INT8)."""

from huggingface_hub import hf_hub_download
from pathlib import Path

def main():
    print("=" * 60)
    print("📥 DOWNLOAD DO MODELO MiniCPM-V 2.6 (GGUF INT8)")
    print("=" * 60)

    repo = "openbmb/MiniCPM-V-2_6-gguf"
    filename = "ggml-model-Q8_0.gguf"  # arquivo multimodal correto

    cache_dir = Path("./models/minicpm-v2_6-int8")
    cache_dir.mkdir(parents=True, exist_ok=True)

    print("🔍 Baixando arquivo...")
    local_path = hf_hub_download(
        repo_id=repo,
        filename=filename,
        local_dir=str(cache_dir),
        local_dir_use_symlinks=False
    )

    print(f"✅ Download concluído!")
    print(f"📁 Arquivo salvo em: {local_path}")
    print("=" * 60)

if __name__ == "__main__":
    main()
