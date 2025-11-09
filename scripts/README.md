# Scripts

## Export API Documentation

Exporta a documentação da API FastAPI para arquivos HTML e JSON/YAML.

### Uso

```bash
python scripts/export_docs.py
```

### Output

Os arquivos são gerados em `docs/api/`:

- **`index.html`** - Documentação interativa ReDoc (recomendado para compartilhar)
- **`swagger.html`** - Documentação interativa Swagger UI
- **`openapi.json`** - Schema OpenAPI em JSON
- **`openapi.yaml`** - Schema OpenAPI em YAML

### Compartilhar Documentação

Os arquivos HTML são standalone e podem ser:
- Abertos diretamente no navegador
- Enviados por email
- Hospedados em qualquer servidor web
- Compartilhados via Google Drive, Dropbox, etc.

---

## Pré-Quantização do Modelo BLIP2

Este script quantiza o modelo BLIP2 para INT8 offline, gerando um arquivo pronto para uso em produção.

### Uso Básico

```bash
# Quantiza modelo (uma vez, offline)
python scripts/quantize_blip2.py
```

Isso gera: `models/blip2-int8-dynamic.pt` (~4 GB)

### Opções

```bash
# Modelo customizado
python scripts/quantize_blip2.py --model Salesforce/blip-base

# Diretório customizado
python scripts/quantize_blip2.py --cache-dir /path/to/models

# Output customizado
python scripts/quantize_blip2.py --output my-model.pt
```

### Benefícios

- **Startup 60% mais rápido**: ~1min ao invés de 2min 30s
- **Consistência**: Mesmo modelo quantizado sempre
- **Deploy otimizado**: Sem quantização em produção
- **Compartilhável**: Time usa mesmo cache

### Deploy

#### Opção 1: Git LFS (modelos <5 GB)

```bash
# Instala Git LFS
git lfs install

# Track arquivo grande
git lfs track "models/blip2-int8-dynamic.pt"
git add .gitattributes
git add models/blip2-int8-dynamic.pt
git commit -m "Add pre-quantized BLIP2 model"
git push
```

#### Opção 2: S3/Storage Externo

```bash
# Upload
aws s3 cp models/blip2-int8-dynamic.pt \
  s3://your-bucket/models/blip2-int8-dynamic.pt

# Download no deploy
aws s3 cp s3://your-bucket/models/blip2-int8-dynamic.pt \
  ./models/blip2-int8-dynamic.pt
```

#### Opção 3: CI/CD Cache

```yaml
# .github/workflows/deploy.yml
- name: Cache quantized model
  uses: actions/cache@v3
  with:
    path: models/blip2-int8-dynamic.pt
    key: blip2-int8-v1
    
- name: Quantize if not cached
  run: |
    if [ ! -f models/blip2-int8-dynamic.pt ]; then
      python scripts/quantize_blip2.py
    fi
```

### Requisitos

O script requer:
- `torch`
- `transformers`
- ~16 GB RAM para quantização
- ~15 GB espaço em disco (modelo original + quantizado)

### Tempo de Execução

- **Primeira vez**: ~2-3 minutos (download + quantização)
- **Com cache**: ~1 minuto (só quantização)

### Troubleshooting

**Erro de memória:**
```bash
# Rode em máquina com mais RAM ou use swap
```

**Modelo não encontrado:**
```bash
# Verifica se modelo existe no HuggingFace
python -c "from transformers import Blip2ForConditionalGeneration; \
           Blip2ForConditionalGeneration.from_pretrained('Salesforce/blip2-opt-2.7b')"
```

**Arquivo corrompido:**
```bash
# Remove e gera novamente
rm models/blip2-int8-dynamic.pt
python scripts/quantize_blip2.py
```
