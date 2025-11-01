# 🏗️ VIRAG-BIM

**Sistema de Monitoramento Automatizado de Obras do Metrô de São Paulo**

Sistema de análise automatizada que compara imagens reais de obras com modelos digitais BIM (IFC), utilizando Vision-Language Models para identificar progresso, desvios e gerar relatórios.

## 🌟 Funcionalidades

- **Processamento de Modelos BIM/IFC**: Upload e extração automática de elementos com IfcOpenShell
- **Análise Visual com VLM**: BLIP-2 quantizado para análise de imagens de obras
- **Comparação Automática**: Detecta elementos visíveis vs. modelo BIM
- **Cálculo de Progresso**: Estimativa percentual de conclusão da obra
- **Alertas Inteligentes**: Identifica elementos faltantes e desvios
- **Busca Vetorial**: CLIP embeddings para similaridade de elementos
- **Cache Inteligente**: Redis para otimizar análises repetidas
- **Arquitetura DI**: Dependency Injection para testabilidade e manutenibilidade
- **Docker Compose**: Deploy simplificado com todos os serviços

## 🏗️ Arquitetura

```
┌─────────────┐      ┌──────────────┐      ┌───────────────┐
│   FastAPI   │─────▶│     VLM      │─────▶│  BIM Analysis │
│   Routes    │      │   Service    │      │    Service    │
└──────┬──────┘      └──────┬───────┘      └───────────────┘
       │                    │
       │                    │
       ▼                    ▼
┌─────────────┐      ┌──────────────┐      ┌───────────────┐
│  DynamoDB   │      │ OpenSearch   │      │      S3       │
│ (Metadata)  │      │  (Vectors)   │      │   (Files)     │
└─────────────┘      └──────────────┘      └───────────────┘
```

### Componentes

1. **FastAPI**: API REST assíncrona com DI
2. **IFCProcessorService**: Processamento de arquivos IFC/BIM
3. **BIMAnalysisService**: Comparação imagem vs. modelo
4. **VLMService**: BLIP-2 para análise visual
5. **EmbeddingService**: CLIP para embeddings vetoriais
6. **DynamoDB**: Armazenamento de projetos, análises e alertas
7. **OpenSearch**: Busca vetorial de elementos BIM
8. **S3/LocalStack**: Armazenamento de IFC e imagens
9. **Redis**: Cache de resultados

## 📋 Pré-requisitos

- Python 3.12+
- Docker e Docker Compose
- 8GB+ RAM (para modelos VLM)

## 🚀 Quick Start

### 1. Clone e Configure

```bash
git clone <repository-url>
cd mss-metro-ai-api-service

# Copie variáveis de ambiente
cp .env.local .env
```

### 2. Instale Dependências

```bash
# Instalar uv
curl -LsSf https://astral.sh/uv/install.sh | sh

# Instalar dependências
uv sync
```

### 3. Inicie Serviços

```bash
# Suba todos os serviços (Redis, OpenSearch, LocalStack, DynamoDB)
docker-compose up -d

# Aguarde inicialização (~30s)
docker-compose logs -f
```

### 4. Crie Tabelas DynamoDB

```bash
uv run python scripts/init_dynamodb_tables.py
```

### 5. Inicie a API

```bash
# Desenvolvimento
uv run task dev

# Ou manualmente
uv run uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

### 6. Acesse a Documentação

Abra: http://localhost:8000/docs

## 📡 API Endpoints

### 1. Upload de Arquivo IFC

**POST** `/bim/upload-ifc`

Upload e processamento de modelo BIM.

```bash
curl -X POST "http://localhost:8000/bim/upload-ifc" \
  -F "file=@modelo-estacao.ifc" \
  -F "project_name=Estação Vila Prudente" \
  -F "description=Expansão Linha 2" \
  -F "location=Vila Prudente, São Paulo"
```

**Response:**
```json
{
  "project_id": "01JXXX...",
  "project_name": "Estação Vila Prudente",
  "s3_key": "bim-projects/01JXXX.../model.ifc",
  "total_elements": 1250,
  "processing_time": 3.45,
  "message": "IFC processado com sucesso"
}
```

### 2. Análise de Imagem de Obra

**POST** `/bim/analyze`

Analisa imagem comparando com modelo BIM.

```bash
curl -X POST "http://localhost:8000/bim/analyze" \
  -F "file=@foto-obra.jpg" \
  -F "project_id=01JXXX..." \
  -F "context=Área de fundação, 3º subsolo"
```

**Response:**
```json
{
  "analysis_id": "01JYYY...",
  "status": "completed",
  "result": {
    "analysis_id": "01JYYY...",
    "project_id": "01JXXX...",
    "image_s3_key": "bim-projects/.../image.jpg",
    "detected_elements": [
      {
        "element_id": "2O2Fr$t4X7Zf8NOew3FLPU",
        "element_type": "Wall",
        "confidence": 0.75,
        "status": "in_progress",
        "description": "Wall detectado na imagem",
        "deviation": null
      }
    ],
    "overall_progress": 45.5,
    "summary": "Descrição técnica da imagem...",
    "alerts": [
      "Slab (laje-nivel-2) não identificado na imagem"
    ],
    "analyzed_at": "2024-11-01T00:00:00",
    "processing_time": 12.3
  }
}
```

### 3. Consultar Progresso do Projeto

**GET** `/bim/progress/{project_id}`

Retorna histórico e progresso.

```bash
curl "http://localhost:8000/bim/progress/01JXXX..."
```

**Response:**
```json
{
  "project_id": "01JXXX...",
  "project_name": "Estação Vila Prudente",
  "total_analyses": 15,
  "analyses": [...],
  "open_alerts": 3,
  "recent_alerts": [...],
  "overall_progress": 52.3,
  "last_analysis_date": "2024-11-01T00:00:00"
}
```

### 4. Health Check

**GET** `/health`

```bash
curl "http://localhost:8000/health"
```

## 🔧 Configuração

### Variáveis de Ambiente (.env)

```bash
# VLM Model
VLM_MODEL_NAME=Salesforce/blip2-opt-2.7b
DEVICE=cpu  # ou cuda
USE_QUANTIZATION=true

# Embedding Model
EMBEDDING_MODEL_NAME=sentence-transformers/clip-ViT-B-32

# DynamoDB
DYNAMODB_ENDPOINT_URL=http://localhost:8000

# S3/LocalStack
S3_ENDPOINT_URL=http://localhost:4566
S3_BUCKET=virag-bim-storage

# OpenSearch
OPENSEARCH_HOSTS=["http://localhost:9200"]

# Redis
REDIS_HOST=localhost
REDIS_PORT=6379
CACHE_TTL=3600
```

## 🔄 Fluxo de Operação

### 1. Upload e Processamento do IFC

```
Usuário → POST /bim/upload-ifc (arquivo IFC)
         ↓
    IFCProcessorService
         ├─ Extrai elementos (Wall, Slab, Column, etc.)
         ├─ Gera JSON estruturado
         └─ Armazena em S3 + DynamoDB
         ↓
    Response: {project_id, total_elements}
```

### 2. Análise de Imagem

```
Usuário → POST /bim/analyze (imagem)
         ↓
    BIMAnalysisService
         ├─ VLMService: gera descrição da imagem
         ├─ Compara com elementos BIM
         ├─ Calcula progresso (%)
         └─ Identifica alertas
         ↓
    Armazena em S3 + DynamoDB
         ↓
    Response: {analysis_id, result}
```

## 🛠️ Desenvolvimento

### Estrutura do Projeto

```
app/
├── core/
│   ├── container.py           # DI Container
│   ├── settings.py            # Configurações
│   └── logger.py              # Logging
├── clients/
│   ├── s3.py                  # Cliente S3
│   ├── dynamodb.py            # Cliente DynamoDB
│   ├── opensearch.py          # Cliente OpenSearch
│   └── cache.py               # Cliente Redis
├── services/
│   ├── ifc_processor.py       # Processamento IFC
│   ├── bim_analysis.py        # Análise BIM
│   ├── vlm_service.py         # VLM (BLIP-2)
│   └── embedding_service.py   # Embeddings (CLIP)
├── routes/
│   ├── bim.py                 # Rotas VIRAG-BIM
│   └── health.py              # Health check
└── schemas/
    └── bim.py                 # Schemas Pydantic

scripts/
└── init_dynamodb_tables.py    # Setup DynamoDB

tests/
└── ...                        # Testes
```

### Comandos Úteis

```bash
# Linting e formatação
uv run task lint
uv run task lint-fix

# Type checking
uv run task type-check

# Testes
uv run task test
uv run task test-cov

# CI completo
uv run task ci
```

### Docker

```bash
# Build e start
docker-compose up -d --build

# Logs
docker-compose logs -f api

# Restart
docker-compose restart api

# Stop
docker-compose down
```

## 📊 Tipos de Elementos Suportados

O sistema identifica automaticamente 13 tipos de elementos BIM:

- **IfcWall** / **IfcWallStandardCase** - Paredes
- **IfcSlab** - Lajes
- **IfcColumn** - Colunas/Pilares
- **IfcBeam** - Vigas
- **IfcDoor** - Portas
- **IfcWindow** - Janelas
- **IfcStair** - Escadas
- **IfcRoof** - Telhados/Cobertura
- **IfcFooting** - Sapatas
- **IfcPile** - Estacas
- **IfcRailing** - Guarda-corpos
- **IfcCurtainWall** - Fachadas cortina

## 🎯 Status de Progresso

O sistema classifica elementos em 5 estados:

- `not_started` - Não iniciado
- `in_progress` - Em andamento
- `completed` - Concluído
- `delayed` - Atrasado
- `deviated` - Desviado do planejado

## ⚡ Otimizações

- **Quantização 8-bit**: Reduz uso de memória do VLM em ~75%
- **Cache Redis**: Evita reprocessamento de análises similares
- **Processamento Assíncrono**: Não bloqueia outras requisições
- **Lazy Loading**: Modelo ML carrega apenas quando necessário
- **Batch Embeddings**: Processa embeddings em lote

## 🧪 Testando

### Exemplo Completo em Python

```python
import requests
from pathlib import Path

API_URL = "http://localhost:8000"

# 1. Upload IFC
with open("modelo.ifc", "rb") as f:
    response = requests.post(
        f"{API_URL}/bim/upload-ifc",
        files={"file": f},
        data={"project_name": "Meu Projeto"}
    )
    project = response.json()
    project_id = project["project_id"]
    print(f"✅ Projeto: {project_id}")
    print(f"📊 Elementos: {project['total_elements']}")

# 2. Analisar imagem
with open("foto-obra.jpg", "rb") as f:
    response = requests.post(
        f"{API_URL}/bim/analyze",
        files={"file": f},
        data={"project_id": project_id}
    )
    analysis = response.json()
    result = analysis["result"]
    print(f"✅ Análise: {analysis['analysis_id']}")
    print(f"📈 Progresso: {result['overall_progress']}%")
    print(f"🔍 Detectados: {len(result['detected_elements'])} elementos")
    print(f"⚠️  Alertas: {len(result['alerts'])}")

# 3. Ver progresso
response = requests.get(f"{API_URL}/bim/progress/{project_id}")
progress = response.json()
print(f"✅ Total de análises: {progress['total_analyses']}")
print(f"📊 Progresso médio: {progress['overall_progress']}%")
```

## 🐛 Troubleshooting

### Erro: "ifcopenshell not found"
```bash
uv pip install ifcopenshell
```

### Erro: DynamoDB connection refused
```bash
docker-compose ps dynamodb
docker-compose restart dynamodb
```

### Performance lenta
- Use GPU: `DEVICE=cuda` no .env
- Reduza resolução das imagens
- Use modelo menor: `VLM_MODEL_NAME=Salesforce/blip2-opt-2.7b`

## 📝 Licença

[Adicionar licença]

## 🤝 Contribuindo

Contribuições são bem-vindas! Abra issues ou pull requests.

## 📖 Documentação Adicional

- [Dependency Injection](https://python-dependency-injector.ets-labs.org/)
- [IfcOpenShell](http://ifcopenshell.org/)
- [FastAPI](https://fastapi.tiangolo.com/)

---

**Desenvolvido para o Metrô de São Paulo** 🚇
