# 🎯 VI-RAG System - Vision-Language Retrieval-Augmented Generation

**Implementação Completa do Sistema VI-RAG para VIRAG-BIM**

**Data:** Novembro 2024  
**Versão:** 2.0.0

---

## 📋 Visão Geral

Sistema avançado que combina **Vision-Language Models (VLM)** com **Retrieval-Augmented Generation (RAG)** para análise automatizada de obras usando modelos BIM como contexto.

### **Fluxo Principal**

```
Upload IFC → Embeddings → OpenSearch
    ↓
Imagem + Descrição → Embedding → RAG Context → VLM Analysis
    ↓
Comparação Automática → Relatório → Alertas → DynamoDB
```

---

## ✅ Componentes Implementados

### 1. **Processamento IFC com Embeddings**

**Arquivo:** `app/services/ifc_processor.py`

**O que faz:**
- Processa arquivo `.ifc` e extrai elementos BIM
- Gera embeddings de **nome + tipo + propriedades** dos elementos
- Armazena **descrição do projeto** como metadado
- Indexa tudo no OpenSearch para busca vetorial

**Método principal:**
```python
await ifc_processor.index_elements_to_opensearch(
    project_id=project_id,
    elements=elementos
)
```

**Modelo OpenSearch:** `BIMElementEmbedding`
- `element_id`, `project_id`, `element_type`
- `description` (nome + tipo + propriedades)
- `properties_text` (metadados)
- `embedding` (vetor 512 dims - CLIP)

---

### 2. **Análise de Imagem com VI-RAG**

**Arquivo:** `app/services/bim_analysis.py`

**Fluxo Detalhado:**

```python
# 1. Gera embedding da IMAGEM (não da descrição!)
image_embedding = await _generate_image_embedding(image_bytes)

# 2. Busca contexto RAG no OpenSearch (KNN search)
rag_context = await _fetch_rag_context(image_embedding, project_id)

# 3. VLM analisa imagem + contexto RAG
vlm_description = await vlm.generate_caption(
    image_bytes,
    prompt_with_rag_context
)

# 4. Fuzzy matching com elementos BIM
detected_elements = await _compare_with_bim_model(
    vlm_description,
    project_data
)

# 5. Busca análise anterior AUTOMATICAMENTE
previous_analysis = await _get_previous_analysis(project_id)

# 6. VLM compara análises
comparison = await _compare_with_previous_analysis(
    current_elements,
    previous_analysis
)

# 7. Gera relatório estruturado
return {
    "detected_elements": [...],
    "overall_progress": 65.5,
    "summary": "...",
    "alerts": [...],
    "comparison": {
        "progress_change": +12.3,
        "elements_added": [...],
        "elements_removed": [...],
        "elements_changed": [...]
    }
}
```

**Novos Métodos:**
- `_generate_image_embedding()` - Embedding da imagem com CLIP
- `_fetch_rag_context()` - Busca KNN no OpenSearch
- `_get_previous_analysis()` - Busca análise mais recente
- `_compare_with_previous_analysis()` - Comparação com VLM

---

### 3. **Schemas Atualizados**

**Arquivo:** `app/schemas/bim.py`

#### **Novos Schemas:**

**`ElementChange`** - Representa mudança em elementos:
```python
{
    "element_id": "...",
    "element_type": "Wall",
    "change_type": "new" | "removed" | "status_change",
    "previous_status": "in_progress",
    "current_status": "completed",
    "description": "Status alterado de in_progress para completed"
}
```

**`AnalysisComparison`** - Comparação entre análises:
```python
{
    "previous_analysis_id": "...",
    "previous_timestamp": "2024-11-01T10:00:00Z",
    "progress_change": +12.3,  # Percentual
    "elements_added": [ElementChange, ...],
    "elements_removed": [ElementChange, ...],
    "elements_changed": [ElementChange, ...],
    "summary": "Progresso significativo em paredes..."  # Gerado pela VLM
}
```

**`ConstructionAnalysis`** - Atualizado:
```python
{
    "analysis_id": "...",
    "project_id": "...",
    "image_s3_key": "...",
    "image_description": "Foto da fachada",  # NOVO: descrição do usuário
    "detected_elements": [...],
    "overall_progress": 65.5,
    "summary": "...",
    "alerts": [...],
    "comparison": AnalysisComparison | None,  # NOVO: comparação automática
    "analyzed_at": "...",
    "processing_time": 2.34
}
```

---

### 4. **Modelos DynamoDB Atualizados**

**Arquivo:** `app/models/dynamodb.py`

#### **`ConstructionAnalysisModel`**
- **Novos campos:**
  - `image_description: UnicodeAttribute(null=True)` - Descrição do usuário
  - `comparison: MapAttribute(null=True)` - Dados de comparação
- **Novo índice:**
  - `project_id_index` (GSI) - Para queries cronológicas

#### **`AlertModel`**
- **Novo índice:**
  - `project_id_index` (GSI) - Para listar alertas por projeto

---

### 5. **Novos Endpoints**

**Arquivo:** `app/routes/bim.py`

#### **GET /bim/projects/{project_id}/alerts**
Lista todos os alertas de um projeto.

**Response:**
```json
{
    "project_id": "01HXYZ...",
    "total_alerts": 15,
    "open_alerts": 8,
    "resolved_alerts": 7,
    "alerts": [
        {
            "alert_id": "01HXYZ...",
            "project_id": "01HXYZ...",
            "analysis_id": "01HXYZ...",
            "alert_type": "missing_element",
            "severity": "medium",
            "title": "Elemento não detectado",
            "description": "Coluna P-003 não visível na imagem",
            "element_id": "2a3b4c5d...",
            "created_at": "2024-11-01T15:30:00Z",
            "resolved": false,
            "resolved_at": null,
            "resolved_by": null
        }
    ]
}
```

#### **GET /bim/projects/{project_id}/reports?limit=50**
Lista todas as análises/relatórios de um projeto.

**Response:**
```json
{
    "project_id": "01HXYZ...",
    "project_name": "Estação Pinheiros",
    "total_reports": 45,
    "latest_progress": 72.5,
    "reports": [
        {
            "analysis_id": "01HXYZ...",
            "project_id": "01HXYZ...",
            "image_s3_key": "bim-projects/.../image.jpg",
            "image_description": "Foto da fachada principal",
            "detected_elements": [...],
            "overall_progress": 72.5,
            "summary": "Progresso significativo observado...",
            "alerts": ["Coluna P-003 não detectada"],
            "comparison": {
                "previous_analysis_id": "01HXYZ...",
                "previous_timestamp": "2024-10-28T10:00:00Z",
                "progress_change": 8.3,
                "elements_added": [...],
                "elements_removed": [],
                "elements_changed": [...],
                "summary": "8.3% de progresso desde última análise..."
            },
            "analyzed_at": "2024-11-01T15:30:00Z",
            "processing_time": 3.45
        }
    ]
}
```

---

### 6. **Endpoint Atualizado**

#### **POST /bim/analyze**
Análise de imagem com VI-RAG completo.

**Request (multipart/form-data):**
```
- file: image.jpg (OBRIGATÓRIO)
- project_id: ULID (OBRIGATÓRIO)
- image_description: "Foto da fachada" (NOVO - OPCIONAL)
- context: "Fase de acabamento" (OPCIONAL)
```

**Processo Interno:**
1. ✅ Valida imagem e project_id
2. ✅ Gera embedding da **imagem**
3. ✅ Busca contexto RAG (elementos similares)
4. ✅ VLM analisa com contexto
5. ✅ Fuzzy matching elementos
6. ✅ Busca análise anterior **automaticamente**
7. ✅ VLM compara análises
8. ✅ Salva embedding no OpenSearch
9. ✅ Salva análise no DynamoDB
10. ✅ Cria alertas estruturados

**Response:** Igual anterior + campo `comparison`

---

### 7. **Salvamento Automático de Alertas**

**Arquivo:** `app/routes/bim.py` - Função `_save_alerts()`

**O que faz:**
- Recebe lista de alertas (strings) da VLM
- Classifica automaticamente por **palavras-chave**:
  - `missing/faltando` → `MISSING_ELEMENT`
  - `delay/atraso` → `DELAY`
  - `quality/qualidade` → `QUALITY_ISSUE`
  - `safety/segurança` → `SAFETY_CONCERN` (HIGH severity)
- Determina severidade:
  - `critical/urgente` → `CRITICAL`
  - `high/importante` → `HIGH`
  - `medium` (padrão) → `MEDIUM`
  - `low/menor` → `LOW`
- Salva cada alerta como registro separado em `AlertModel`

**Histórico completo de alertas mantido! ✅**

---

### 8. **Modelo OpenSearch para Imagens**

**Arquivo:** `app/models/opensearch.py`

**`ImageAnalysisDocument`** - Atualizado:
```python
{
    "analysis_id": "...",
    "project_id": "...",
    "image_s3_key": "...",
    "image_description": "Foto da fachada",  # NOVO: metadado
    "overall_progress": "72.5",
    "summary": "...",
    "image_embedding": [0.123, ...],  # 512 dims
    "analyzed_at": "2024-11-01T15:30:00Z"
}
```

**Permite buscar imagens similares!**

---

## 🚀 Como Usar

### **1. Upload IFC (com indexação automática)**
```bash
curl -X POST http://localhost:8000/bim/upload-ifc \
  -F "file=@modelo.ifc" \
  -F "project_name=Estação Pinheiros" \
  -F "description=Projeto de expansão da Linha 4"
```

**O que acontece:**
- ✅ Processa IFC
- ✅ Gera embeddings (nome + tipo + props)
- ✅ Indexa no OpenSearch
- ✅ Salva projeto no DynamoDB

---

### **2. Análise VI-RAG Completa**
```bash
curl -X POST http://localhost:8000/bim/analyze \
  -F "file=@foto_obra.jpg" \
  -F "project_id=01HXYZ..." \
  -F "image_description=Foto da fachada leste" \
  -F "context=Fase de acabamento externo"
```

**O que acontece:**
1. ✅ Embedding da imagem (CLIP)
2. ✅ Busca RAG: elementos similares no OpenSearch
3. ✅ VLM analisa com contexto RAG
4. ✅ Fuzzy matching com BIM
5. ✅ **Busca análise anterior automaticamente**
6. ✅ **VLM compara: progresso, mudanças, novos/removidos**
7. ✅ Salva embedding no OpenSearch
8. ✅ Salva análise + comparação no DynamoDB
9. ✅ **Cria alertas estruturados automaticamente**

---

### **3. Listar Alertas**
```bash
curl http://localhost:8000/bim/projects/01HXYZ.../alerts
```

---

### **4. Listar Relatórios**
```bash
curl http://localhost:8000/bim/projects/01HXYZ.../reports?limit=20
```

---

## 📊 Arquitetura VI-RAG

```
┌─────────────────────────────────────────────────────────────┐
│                     UPLOAD IFC                              │
│  Arquivo.ifc → Processar → Embeddings → OpenSearch         │
└─────────────────────────────────────────────────────────────┘
                            ↓
┌─────────────────────────────────────────────────────────────┐
│                   ANÁLISE VI-RAG                             │
│                                                              │
│  1. Imagem → CLIP Embedding                                 │
│  2. KNN Search → OpenSearch (RAG Context)                   │
│  3. VLM(Imagem + RAG Context) → Descrição                   │
│  4. Fuzzy Match → Elementos BIM                             │
│  5. Query DynamoDB → Análise Anterior                       │
│  6. VLM(Atual vs Anterior) → Comparação                     │
│  7. Save Embedding → OpenSearch                             │
│  8. Save Análise + Comparação → DynamoDB                    │
│  9. Parse & Save Alertas → DynamoDB (AlertModel)            │
└─────────────────────────────────────────────────────────────┘
                            ↓
┌─────────────────────────────────────────────────────────────┐
│                   CONSULTAS                                  │
│  GET /projects/{id}/alerts                                  │
│  GET /projects/{id}/reports                                 │
└─────────────────────────────────────────────────────────────┘
```

---

## 🎯 Benefícios

### **1. Contexto Enriquecido (RAG)**
- Busca elementos BIM relevantes **antes** da análise
- VLM tem contexto específico do projeto
- Reduz alucinações, aumenta precisão

### **2. Comparação Automática**
- **Não precisa** especificar análise anterior
- Sistema busca automaticamente a mais recente
- VLM identifica mudanças, progresso, regressões

### **3. Histórico Completo**
- Análises cronológicas no DynamoDB (GSI)
- Comparações entre análises consecutivas
- Alertas separados com classificação automática

### **4. Busca Vetorial Multimodal**
- Embeddings de elementos IFC
- Embeddings de imagens
- Busca por similaridade visual e textual

### **5. Metadados Contextuais**
- Descrição do projeto (metadado IFC)
- Descrição da imagem (metadado análise)
- Preserva contexto sem poluir embeddings

---

## 📝 Dependências

**Nenhuma nova dependência!** ✅

Tudo implementado com as bibliotecas existentes:
- `opensearch-py` / `opensearch-dsl`
- `pynamodb`
- `rapidfuzz` (já adicionado anteriormente)
- `sentence-transformers` (CLIP)
- `transformers` (BLIP-2)

---

## 🔧 Configuração

### **1. Inicializar OpenSearch**
```python
from app.models.opensearch import configure_opensearch, init_indices

configure_opensearch(
    hosts=["http://localhost:9200"],
    use_ssl=False,
    verify_certs=False
)

init_indices()  # Cria índices BIMElementEmbedding e ImageAnalysisDocument
```

### **2. Configurar DynamoDB**
```python
from app.models.dynamodb import configure_models, create_tables_if_not_exist

configure_models("http://localhost:4566")  # LocalStack
create_tables_if_not_exist()
```

---

## ⚠️ Considerações Importantes

### **1. Análise Anterior**
- Primeira análise de um projeto **não terá** campo `comparison`
- Análises subsequentes sempre incluem comparação automática

### **2. Embeddings de Imagem**
- Requer `EmbeddingService.generate_image_embedding()`
- Se não implementado, precisa adaptar para usar CLIP diretamente

### **3. VLM para Comparação**
- Usa `VLMService.generate_text()` para resumo de comparação
- Se não existir, criar método wrapper para geração de texto

### **4. Índices DynamoDB (GSI)**
- Ao criar tabelas pela primeira vez, os GSI são criados
- Se tabelas já existem, pode ser necessário adicionar GSI manualmente

---

## 🚧 Próximos Passos (Opcionais)

### **Baixa Prioridade:**
- [ ] Cache de embeddings para mesmos elementos
- [ ] Reranking dos resultados RAG (cross-encoder)
- [ ] Structured Output com LangChain (Pydantic)
- [ ] Métricas de similaridade entre análises
- [ ] Sugestões automáticas de próximas ações

---

## 📖 Documentação Adicional

- [README Principal](VIRAG-BIM-README.md)
- [Melhorias Anteriores](IMPROVEMENTS.md)
- [Quick Start](QUICKSTART.md)
- [Status do Projeto](STATUS.md)

---

**✨ VIRAG-BIM v2.0.0 - Sistema VI-RAG Completo**

**🚇 Desenvolvido para o Metrô de São Paulo**

**🎯 Monitoramento Inteligente de Obras com Visão Computacional + RAG**
