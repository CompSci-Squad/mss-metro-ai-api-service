# 🏗️ VIRAG-BIM

**Sistema de Monitoramento Automatizado de Obras - Metrô de São Paulo**

Análise automatizada de obras usando Vision-Language Models e modelos BIM (IFC).

## Stack

- **FastAPI** + **DynamoDB** (Análises/Alertas) + **OpenSearch** + **Redis**
- **VLM:** BLIP-2 quantizado
- **Embeddings:** CLIP (sentence-transformers)
- **IFC:** IfcOpenShell

## Quick Start

```bash
# Setup
cp .env.local .env
uv sync

# Serviços
docker-compose up -d

# Tabelas
uv run python scripts/init_dynamodb_tables.py

# API
uv run task dev
```

**Docs:** http://localhost:8000/docs

## Endpoints

### Upload IFC
```bash
POST /bim/upload-ifc
curl -X POST "http://localhost:8000/bim/upload-ifc" \
  -F "file=@modelo.ifc" \
  -F "project_name=Estação XYZ"
```

### Análise de Imagem
```bash
POST /bim/analyze
curl -X POST "http://localhost:8000/bim/analyze" \
  -F "file=@foto.jpg" \
  -F "project_id=01JXXX..." \
  -F "image_description=Fachada principal"
```

### Listar Alertas
```bash
GET /bim/projects/{project_id}/alerts
```

### Listar Relatórios
```bash
GET /bim/projects/{project_id}/reports
```

## Sistema VI-RAG

O sistema implementa **Vision-Language Retrieval-Augmented Generation**:

1. **Upload IFC** → Gera embeddings dos elementos → Indexa no OpenSearch
2. **Análise de Imagem** → Embedding da imagem → Busca RAG contexto → VLM analisa com contexto
3. **Comparação Automática** → Busca análise anterior → VLM compara → Gera relatório com mudanças
4. **Alertas Estruturados** → Classifica automaticamente → Salva no DynamoDB

Veja detalhes completos em `VIRAG-IMPLEMENTATION.md`.

---

**Desenvolvido para o Metrô de São Paulo** 🚇
