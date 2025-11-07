# 📚 Documentação Swagger - VIRAG-BIM API

## ✅ Resumo

Toda a API foi documentada com **Swagger/OpenAPI** detalhado, incluindo:

- ✅ Descrições completas de cada endpoint
- ✅ Exemplos de request e response
- ✅ Documentação de erros possíveis
- ✅ Tags organizadas por funcionalidade
- ✅ Tipos de dados validados com Pydantic
- ✅ Códigos de status HTTP apropriados

---

## 🌐 Acesso ao Swagger

Após iniciar a aplicação:

```bash
# Inicia servidor
uv run task dev

# Acessa documentação interativa
http://localhost:8000/docs        # Swagger UI (interface visual)
http://localhost:8000/redoc       # ReDoc (alternativa mais limpa)
http://localhost:8000/openapi.json # JSON da especificação OpenAPI
```

---

## 📋 Tags e Organização

### 🏗️ **Projetos**
Upload e processamento de arquivos IFC

- `POST /bim/upload-ifc` - Upload de arquivo IFC

### 🔍 **Análise**
Análise de imagens usando VI-RAG

- `POST /bim/analyze` - Análise de imagem da obra

### 📊 **Progresso**
Consulta de progresso e timeline

- `GET /bim/progress/{project_id}` - Progresso do projeto
- `GET /bim/timeline/{project_id}` - Timeline cronológica

### 🔄 **Comparação**
Comparação entre múltiplas análises

- `GET /bim/compare/{project_id}` - Comparar análises

### 🔔 **Alertas**
Gerenciamento de alertas e relatórios

- `GET /bim/projects/{project_id}/alerts` - Listar alertas
- `GET /bim/projects/{project_id}/reports` - Listar relatórios

### 💚 **Saúde**
Healthchecks da aplicação

- `GET /health` - Healthcheck básico
- `GET /health/detailed` - Healthcheck detalhado

---

## 📝 Detalhamento por Endpoint

### 1. **POST /bim/upload-ifc**

**Funcionalidade:** Upload e processamento de arquivo IFC

**Parâmetros:**
- `file` (form-data): Arquivo IFC (max 100MB)
- `project_name` (form-data): Nome do projeto (3-100 chars)
- `description` (form-data, opcional): Descrição do projeto
- `location` (form-data, opcional): Localização da obra

**Response 201:**
```json
{
  "project_id": "01HXYZ123ABC",
  "project_name": "Edifício Residencial ABC",
  "s3_key": "bim-projects/01HXYZ123ABC/model.ifc",
  "total_elements": 245,
  "processing_time": 18.45,
  "message": "IFC processado com sucesso"
}
```

**Erros:**
- `400`: Arquivo inválido, nome de projeto inválido
- `500`: Erro no processamento do IFC

**Processamento:**
1. Validação do arquivo (extensão .ifc, tamanho max 100MB)
2. Extração de elementos BIM (IfcOpenShell)
3. Geração de embeddings usando CLIP
4. Upload para S3
5. Salva metadados no DynamoDB
6. Indexação vetorial no OpenSearch

**Tempo estimado:**
- Pequeno (< 100 elementos): ~5-10s
- Médio (100-500 elementos): ~15-30s
- Grande (> 500 elementos): ~30-60s

---

### 2. **POST /bim/analyze**

**Funcionalidade:** Análise de imagem da obra usando VI-RAG

**Parâmetros:**
- `file` (form-data): Imagem (JPG, PNG, BMP, TIFF - max 100MB)
- `project_id` (form-data): ID do projeto BIM (ULID)
- `image_description` (form-data, opcional): Descrição da imagem
- `context` (form-data, opcional): Contexto adicional

**Response 200:**
```json
{
  "analysis_id": "01HXYZ456DEF",
  "status": "completed",
  "message": "Análise concluída com sucesso",
  "result": {
    "analysis_id": "01HXYZ456DEF",
    "project_id": "01HXYZ123ABC",
    "image_s3_key": "bim-projects/.../01HXYZ456DEF.jpg",
    "image_description": "Estrutura de concreto - pilares e vigas",
    "detected_elements": [
      {
        "element_id": "2O2Fr$t4X7Zf8NOew3FLOH",
        "element_type": "IfcColumn",
        "confidence": 0.89,
        "status": "completed",
        "description": "Pilar de concreto detectado",
        "deviation": null
      }
    ],
    "overall_progress": 67.5,
    "summary": "A imagem mostra 3 pilares completos...",
    "alerts": ["IfcWall (Parede Norte) não identificado"],
    "comparison": {
      "previous_analysis_id": "01HXYZ789GHI",
      "progress_change": 12.5,
      "elements_changed": [...]
    },
    "analyzed_at": "2024-11-07T14:20:00Z",
    "processing_time": 12.34
  }
}
```

**Erros:**
- `400`: Formato inválido, arquivo muito grande, ID inválido
- `404`: Projeto não encontrado
- `500`: Erro no processamento da análise

**Tecnologia VI-RAG:**
1. Geração de Embedding da Imagem (CLIP)
2. Busca RAG - Contexto vetorial do OpenSearch
3. Análise VLM - BLIP-2 descreve a imagem
4. Detecção de Elementos - Matching vetorial + fuzzy
5. Cálculo de Progresso - Percentual baseado em status
6. Comparação Temporal - Identifica mudanças vs anterior
7. Identificação de Alertas - Desvios e elementos faltantes

**Cálculo de Progresso:**
```
progresso = (completos * 1.0 + em_progresso * 0.5) / total_elementos * 100
```

**Tempo estimado:**
- Imagem pequena (< 2MB): ~5-8s
- Imagem média (2-10MB): ~8-15s
- Imagem grande (> 10MB): ~15-25s

**Dicas para melhores resultados:**
1. **Iluminação**: Boa luz natural ou artificial
2. **Ângulo**: Frontal ou lateral para capturar estrutura
3. **Resolução**: Mínimo 1920x1080 (Full HD)
4. **Foco**: Imagem nítida sem blur
5. **Contexto**: Adicione descrição para melhor precisão

---

### 3. **GET /bim/progress/{project_id}**

**Funcionalidade:** Retorna progresso e histórico do projeto

**Parâmetros:**
- `project_id` (path): ID do projeto (ULID)

**Response 200:**
```json
{
  "project_id": "01HXYZ123ABC",
  "project_name": "Edifício Residencial ABC",
  "total_analyses": 5,
  "analyses": [
    {
      "analysis_id": "01HXYZ456DEF",
      "overall_progress": 67.5,
      "summary": "3 pilares completos...",
      "analyzed_at": "2024-11-07T14:20:00Z"
    }
  ],
  "open_alerts": 3,
  "recent_alerts": [...],
  "overall_progress": 61.25,
  "last_analysis_date": "2024-11-07T14:20:00Z"
}
```

**Informações retornadas:**
- **Progresso geral**: Média de todas as análises
- **Total de análises**: Quantas vezes analisado
- **Histórico**: Lista completa de análises
- **Alertas abertos**: Quantidade não resolvidos
- **Alertas recentes**: Últimos 10
- **Última análise**: Data mais recente

**Cálculo do progresso geral:**
```
progresso_geral = soma(progresso_de_cada_analise) / total_analises
```

---

### 4. **GET /bim/timeline/{project_id}**

**Funcionalidade:** Timeline cronológica do projeto

**Parâmetros:**
- `project_id` (path): ID do projeto (ULID)

**Response 200:**
```json
{
  "project_id": "01HXYZ123ABC",
  "project_name": "Edifício Residencial ABC",
  "timeline": [
    {
      "timestamp": "2024-11-01T09:00:00Z",
      "analysis_id": "01HXYZ111AAA",
      "progress": 25.0,
      "summary": "Fundação iniciada",
      "image_url": "s3://...",
      "detected_elements_count": 12,
      "alerts_count": 1
    }
  ],
  "progress_evolution": [
    {"index": 1, "date": "2024-11-01", "progress": 25.0},
    {"index": 2, "date": "2024-11-05", "progress": 55.0}
  ],
  "total_analyses": 3,
  "current_progress": 67.5,
  "velocity": 7.08,
  "velocity_unit": "% por dia"
}
```

**Velocidade do progresso:**
```
velocidade = (progresso_final - progresso_inicial) / dias_decorridos
```

**Exemplo:** 40% em 20 dias = 2% por dia

**Uso sugerido:**
- Gráfico de linha com `progress_evolution`
- Monitorar velocidade de execução
- Identificar períodos de baixa produtividade

---

### 5. **GET /bim/compare/{project_id}**

**Funcionalidade:** Compara múltiplas análises lado a lado

**Parâmetros:**
- `project_id` (path): ID do projeto (ULID)
- `analysis_ids` (query): IDs separados por vírgula (ex: "id1,id2,id3")

**Exemplo:**
```
GET /bim/compare/01HXYZ123ABC?analysis_ids=id1,id2,id3
```

**Response 200:**
```json
{
  "project_id": "01HXYZ123ABC",
  "project_name": "Edifício Residencial ABC",
  "comparisons": [
    {
      "analysis_id": "01HXYZ111AAA",
      "timestamp": "2024-11-01T09:00:00Z",
      "progress": 25.0,
      "summary": "Fundação iniciada",
      "detected_elements": [...],
      "alerts": [...]
    }
  ],
  "differences": [
    {
      "from": "01HXYZ111AAA",
      "to": "01HXYZ789GHI",
      "progress_change": 30.0,
      "new_alerts": 1
    }
  ]
}
```

**Diferenças calculadas:**
- **progress_change**: Variação percentual do progresso
- **new_alerts**: Quantidade de novos alertas

**Observações:**
- Análises ordenadas automaticamente por data
- Análises não encontradas são ignoradas
- Mínimo de 1 análise válida é necessário

---

### 6. **GET /bim/projects/{project_id}/alerts**

**Funcionalidade:** Lista todos os alertas do projeto

**Parâmetros:**
- `project_id` (path): ID do projeto (ULID)

**Response 200:**
```json
{
  "project_id": "01HXYZ123ABC",
  "total_alerts": 8,
  "open_alerts": 3,
  "resolved_alerts": 5,
  "alerts": [
    {
      "alert_id": "01HXYZ999XXX",
      "project_id": "01HXYZ123ABC",
      "analysis_id": "01HXYZ456DEF",
      "alert_type": "missing_element",
      "severity": "medium",
      "title": "Elemento não detectado",
      "description": "IfcWall (Parede Norte) não identificado",
      "element_id": "2O2Fr$t4X7Zf8NOew3FLOH",
      "created_at": "2024-11-07T14:20:30Z",
      "resolved": false,
      "resolved_at": null,
      "resolved_by": null
    }
  ]
}
```

**Tipos de alertas:**
- `delay`: Atraso na execução
- `deviation`: Desvio do planejado
- `quality_issue`: Problema de qualidade
- `safety_concern`: Preocupação de segurança
- `missing_element`: Elemento esperado não detectado

**Severidade:**
- `low`: Baixa prioridade
- `medium`: Média prioridade
- `high`: Alta prioridade
- `critical`: Crítico - requer ação imediata

---

### 7. **GET /bim/projects/{project_id}/reports**

**Funcionalidade:** Lista todas as análises/relatórios

**Parâmetros:**
- `project_id` (path): ID do projeto (ULID)
- `limit` (query, opcional): Quantidade de resultados (default: 50)

**Exemplo:**
```
GET /bim/projects/01HXYZ123ABC/reports?limit=20
```

**Response 200:**
```json
{
  "project_id": "01HXYZ123ABC",
  "project_name": "Edifício Residencial ABC",
  "total_reports": 5,
  "latest_progress": 67.5,
  "reports": [
    {
      "analysis_id": "01HXYZ456DEF",
      "project_id": "01HXYZ123ABC",
      "detected_elements": [...],
      "overall_progress": 67.5,
      "summary": "3 pilares completos...",
      "alerts": [...],
      "comparison": {...},
      "analyzed_at": "2024-11-07T14:20:00Z"
    }
  ]
}
```

**Ordenação:**
- Relatórios ordenados por data (mais recentes primeiro)

**Uso sugerido:**
- **Dashboard**: Últimos 10 relatórios (limit=10)
- **Histórico completo**: limit=999
- **Timeline**: Usar com gráfico de evolução

---

### 8. **GET /health**

**Funcionalidade:** Healthcheck básico

**Response 200:**
```json
{
  "status": "ok",
  "service": "VIRAG-BIM",
  "timestamp": 1699459200.123
}
```

**Uso:**
- Monitoramento básico de disponibilidade
- Load balancers
- Uptime checkers

---

### 9. **GET /health/detailed**

**Funcionalidade:** Healthcheck detalhado de todos os serviços

**Response 200:**
```json
{
  "status": "healthy",
  "service": "VIRAG-BIM",
  "timestamp": 1699459200.123,
  "total_check_time_ms": 245.67,
  "checks": {
    "redis": {
      "status": "healthy",
      "latency_ms": 12.34
    },
    "s3": {
      "status": "healthy",
      "latency_ms": 45.67
    },
    "dynamodb": {
      "status": "healthy",
      "latency_ms": 89.12,
      "tables_exist": true
    },
    "opensearch": {
      "status": "healthy",
      "latency_ms": 56.78,
      "cluster_status": "green",
      "nodes": 1
    },
    "ml_models": {
      "status": "healthy",
      "latency_ms": 41.76,
      "vlm_loaded": true,
      "embeddings_loaded": true,
      "vlm_model": "Salesforce/blip2-opt-2.7b",
      "embedding_model": "openai/clip-vit-base-patch32"
    }
  }
}
```

**Componentes verificados:**
1. **Redis**: Cache de resultados
2. **S3/LocalStack**: Storage de arquivos
3. **DynamoDB**: Banco de dados NoSQL
4. **OpenSearch**: Busca vetorial (embeddings)
5. **ML Models**: Modelos VLM e CLIP carregados

**Status possíveis:**
- `healthy`: Serviço funcionando perfeitamente
- `degraded`: Serviço funcionando parcialmente
- `unhealthy`: Serviço indisponível
- `unknown`: Status não pôde ser determinado

---

## 🎨 Interface Swagger UI

### Recursos da Interface:

1. **Try it out**: Teste endpoints diretamente do navegador
2. **Schemas**: Visualize modelos de dados Pydantic
3. **Examples**: Veja exemplos de request/response
4. **Authorization**: Configure autenticação (quando implementada)
5. **Download**: Baixe especificação OpenAPI JSON/YAML

### Captura de Tela:

```
┌─────────────────────────────────────────────────────┐
│  VIRAG-BIM API                             v1.0.0   │
│  Sistema Inteligente de Monitoramento de Obras      │
├─────────────────────────────────────────────────────┤
│  Tags                                               │
│  ▼ Projetos       Upload e processamento IFC       │
│  ▼ Análise        Análise de imagens (VI-RAG)      │
│  ▼ Progresso      Consulta de progresso            │
│  ▼ Comparação     Comparação entre análises        │
│  ▼ Alertas        Gerenciamento de alertas         │
│  ▼ Saúde          Healthchecks                     │
└─────────────────────────────────────────────────────┘
```

---

## 🔧 Recursos Adicionados

### 1. **Metadados da API**

No `main.py`:
- Título: "VIRAG-BIM API"
- Descrição completa com markdown
- Versão: 1.0.0
- Tags organizadas
- Informações de contato e licença

### 2. **Documentação por Endpoint**

Para cada endpoint foi adicionado:
- ✅ `tags`: Organização por categoria
- ✅ `summary`: Título curto
- ✅ `description`: Descrição detalhada com markdown
- ✅ `responses`: Exemplos de responses (200, 400, 404, 500)
- ✅ Parâmetros documentados com tipos e descrições

### 3. **Validações Pydantic**

Todos os schemas em `app/schemas/bim.py` incluem:
- `Field()` com descrições
- Validações de tipo
- Valores padrão
- Enums para valores fixos

### 4. **Exemplos Realistas**

Todos os exemplos usam:
- ULIDs realistas
- Dados plausíveis de construção
- Timestamps ISO 8601
- Estruturas JSON válidas

---

## 📊 Estatísticas da Documentação

- **Total de endpoints**: 9
- **Tags organizadas**: 6
- **Exemplos de response**: 27+
- **Schemas Pydantic**: 15+
- **Linhas de documentação**: ~1500+

---

## 🚀 Próximos Passos (Opcional)

Se quiser melhorar ainda mais a documentação:

1. **Autenticação**: Adicionar security schemes (JWT, API Key)
2. **Rate Limiting**: Documentar limites de requisições
3. **Webhooks**: Se implementados futuramente
4. **Versioning**: Suporte a múltiplas versões da API
5. **Exemplos de Código**: Snippets em Python, JavaScript, cURL
6. **Postman Collection**: Exportar coleção para Postman

---

## 📚 Recursos Adicionais

### Documentação OpenAPI:
- [Swagger/OpenAPI Specification](https://swagger.io/specification/)
- [FastAPI Documentation](https://fastapi.tiangolo.com/)
- [Pydantic Documentation](https://docs.pydantic.dev/)

### Ferramentas Úteis:
- **Swagger Editor**: https://editor.swagger.io/
- **OpenAPI Generator**: https://openapi-generator.tech/
- **Postman**: Importar OpenAPI JSON

---

## ✅ Checklist de Qualidade

- ✅ Todas as rotas documentadas
- ✅ Exemplos realistas de request/response
- ✅ Códigos de status HTTP corretos
- ✅ Descrições detalhadas em português
- ✅ Tags organizadas por funcionalidade
- ✅ Schemas Pydantic validados
- ✅ Erros possíveis documentados
- ✅ Tempos de processamento estimados
- ✅ Fórmulas de cálculo explicadas
- ✅ Dicas de uso para cada endpoint

---

**Data:** 2025-11-07  
**Versão da API:** 1.0.0  
**Status:** ✅ Documentação completa  
**Acesso:** http://localhost:8000/docs
