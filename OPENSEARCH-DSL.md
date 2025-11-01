## 🔍 OpenSearch-DSL (ORM para Busca Vetorial)

## ✅ Melhorias Implementadas

### **OpenSearch-DSL** - ORM estilo SQLAlchemy para OpenSearch

Substituímos o cliente opensearch-py manual por **OpenSearch-DSL**, um DSL (Domain Specific Language) que torna queries e documentos type-safe e pythônicos.

#### Antes (cliente manual):
```python
# Código verboso
client.index(
    index="embeddings",
    body={
        "element_id": "123",
        "embedding": [0.1, 0.2, ...],
        "description": "Wall element"
    }
)
```

#### Depois (OpenSearch-DSL):
```python
# Código limpo e tipo-safe
embedding = BIMElementEmbedding(
    element_id="123",
    embedding=[0.1, 0.2, ...],
    description="Wall element"
)
embedding.save()  # created_at automático!
```

---

## 📦 Models Criados

### `app/models/opensearch.py`

Dois documents declarativos:

#### 1. BIMElementEmbedding
```python
class BIMElementEmbedding(Document):
    """Embeddings de elementos BIM para busca vetorial."""
    
    element_id = Keyword(required=True)
    project_id = Keyword(required=True)
    element_type = Keyword(required=True)
    description = Text(analyzer="standard")
    element_name = Text(analyzer="standard")
    
    # Vetor 512 dimensões (CLIP)
    embedding = DenseVector(dims=512)
    
    created_at = Date(default_timezone="UTC")
    updated_at = Date(default_timezone="UTC")
    
    class Index:
        name = "bim_element_embeddings"
        settings = {
            "index": {"knn": True}  # KNN habilitado!
        }
```

#### 2. ImageAnalysisDocument
```python
class ImageAnalysisDocument(Document):
    """Análises de imagens para busca visual."""
    
    analysis_id = Keyword(required=True)
    project_id = Keyword(required=True)
    image_s3_key = Keyword(required=True)
    summary = Text(analyzer="standard")
    
    # Embedding da imagem
    image_embedding = DenseVector(dims=512)
    
    analyzed_at = Date(default_timezone="UTC")
    
    class Index:
        name = "construction_analyses"
        settings = {"index": {"knn": True}}
```

---

## 🔧 Como Usar

### Configurar Conexão
```python
from app.models.opensearch import configure_opensearch

configure_opensearch(
    hosts=["http://localhost:9200"],
    use_ssl=False,
    verify_certs=False
)
```

### Criar Índices
```bash
uv run python scripts/init_opensearch_indices.py
```

Saída:
```
🔧 Configurando OpenSearch: http://localhost:9200
📦 Criando índices OpenSearch...
⏳ Criando bim_element_embeddings (Embeddings de Elementos BIM)...
✓ bim_element_embeddings criado com sucesso!
   • Shards: 1
   • KNN habilitado: True
✅ Todos os índices foram processados!
🚀 OpenSearch pronto para busca vetorial!
```

---

## 💾 Operações CRUD

### Criar (Index)
```python
from app.models.opensearch import BIMElementEmbedding

# Criar embedding
embedding = BIMElementEmbedding(
    element_id="2O2Fr$t4X7Zf8NOew3FLPU",
    project_id="01JXXX...",
    element_type="Wall",
    description="Concrete wall, 20cm thickness",
    element_name="Wall-001",
    embedding=[0.1, 0.2, 0.3, ...],  # 512 dims
)
embedding.save()  # Salva no OpenSearch
```

### Buscar por ID (Get)
```python
# Buscar por ID
embedding = BIMElementEmbedding.get(id="doc_id")

print(embedding.description)
print(embedding.element_type)
```

### Atualizar (Update)
```python
embedding = BIMElementEmbedding.get(id="doc_id")
embedding.description = "Updated description"
embedding.save()  # updated_at automático!
```

### Deletar (Delete)
```python
embedding = BIMElementEmbedding.get(id="doc_id")
embedding.delete()
```

---

## 🔍 Busca Vetorial (KNN)

### Busca por Similaridade

```python
# Vetor de consulta (ex: embedding de uma imagem)
query_vector = [0.1, 0.2, 0.3, ...]  # 512 dims

# Busca os 10 elementos mais similares
results = BIMElementEmbedding.search_by_vector(
    query_embedding=query_vector,
    size=10,
    project_id="01JXXX..."  # Opcional: filtrar por projeto
)

# Iterar resultados
for hit in results:
    print(f"Element: {hit.element_type}")
    print(f"Score: {hit.meta.score}")
    print(f"Description: {hit.description}")
```

### Busca Textual (Full-Text)

```python
# Busca por texto
results = BIMElementEmbedding.search_by_text(
    query_text="concrete wall 20cm",
    size=10,
    project_id="01JXXX..."
)

for hit in results:
    print(f"Found: {hit.element_name} - {hit.description}")
    print(f"Relevance: {hit.meta.score}")
```

---

## 🎯 Busca Híbrida (Texto + Vetor)

```python
from opensearch_dsl import Q, Search

# Combina busca textual e vetorial
search = BIMElementEmbedding.search()

# Busca vetorial (KNN)
knn_query = {
    "knn": {
        "embedding": {
            "vector": query_vector,
            "k": 10
        }
    }
}

# Busca textual
text_query = Q("match", description="concrete wall")

# Combinar (score híbrido)
search = search.query(text_query).update_from_dict({"query": {"knn": knn_query}})

results = search[:10].execute()
```

---

## 📊 Aggregations (Estatísticas)

```python
from opensearch_dsl import A

# Contar elementos por tipo
search = BIMElementEmbedding.search()
search.aggs.bucket('by_type', 'terms', field='element_type')

response = search.execute()

# Resultados
for bucket in response.aggregations.by_type.buckets:
    print(f"{bucket.key}: {bucket.doc_count} elementos")
```

---

## 🔄 Bulk Operations

```python
from opensearch_dsl import bulk

# Criar múltiplos documentos
actions = []
for i in range(100):
    embedding = BIMElementEmbedding(
        element_id=f"elem_{i}",
        project_id="01JXXX...",
        element_type="Wall",
        embedding=generate_embedding(),  # Função fictícia
    )
    actions.append(embedding.to_dict(include_meta=True))

# Bulk insert
bulk(client, actions)
```

---

## 🎨 Query DSL Pythônico

```python
from opensearch_dsl import Q, Search

# Query complexa pythônica
search = BIMElementEmbedding.search()

# Filtros combinados
search = search.filter('term', project_id='01JXXX...')
search = search.filter('terms', element_type=['Wall', 'Slab'])
search = search.filter('range', created_at={'gte': '2024-01-01'})

# Ordenação
search = search.sort('-created_at')

# Paginação
search = search[0:20]  # Primeiros 20 resultados

# Executar
results = search.execute()
```

---

## 📈 Vantagens do OpenSearch-DSL

| Feature | Cliente Manual | OpenSearch-DSL |
|---------|----------------|----------------|
| **Código** | ~80 linhas | ~20 linhas |
| **Type Safety** | ❌ | ✅ |
| **Autocomplete** | ❌ | ✅ |
| **Queries** | JSON verboso | Pythônico |
| **Mapeamentos** | Manual | Automático |
| **Validação** | Manual | Automática |
| **KNN/Vetores** | Complexo | Simples |

---

## 🧪 Exemplo Completo: Busca de Elementos BIM

```python
from app.models.opensearch import BIMElementEmbedding, configure_opensearch
from app.services.embedding_service import EmbeddingService

# 1. Configurar OpenSearch
configure_opensearch(hosts=["http://localhost:9200"])

# 2. Criar índice (primeira vez)
from app.models.opensearch import init_indices
init_indices()

# 3. Indexar elementos BIM
elements = [
    {"id": "elem_1", "type": "Wall", "desc": "Concrete wall"},
    {"id": "elem_2", "type": "Slab", "desc": "Reinforced slab"},
    {"id": "elem_3", "type": "Column", "desc": "Steel column"},
]

embedding_service = EmbeddingService()

for elem in elements:
    # Gerar embedding
    embedding_vector = await embedding_service.generate_embedding(elem["desc"])
    
    # Criar documento
    doc = BIMElementEmbedding(
        element_id=elem["id"],
        project_id="01JXXX...",
        element_type=elem["type"],
        description=elem["desc"],
        embedding=embedding_vector
    )
    doc.save()
    print(f"✓ {elem['id']} indexado")

# 4. Buscar por imagem (vetor)
image_embedding = await embedding_service.generate_image_embedding(image_bytes)

results = BIMElementEmbedding.search_by_vector(
    query_embedding=image_embedding,
    size=5,
    project_id="01JXXX..."
)

print(f"\n🔍 Encontrados {results.count()} elementos similares:")
for hit in results:
    print(f"  • {hit.element_type}: {hit.description} (score: {hit.meta.score:.2f})")
```

---

## 🚀 Setup

### 1. Instalar
```bash
uv sync  # Instala opensearch-dsl
```

### 2. Iniciar OpenSearch
```bash
docker-compose up -d opensearch
```

### 3. Criar Índices
```bash
uv run python scripts/init_opensearch_indices.py
```

### 4. Usar na API
```python
# app/main.py (startup)
from app.models.opensearch import configure_opensearch, init_indices

@app.on_event("startup")
async def startup():
    configure_opensearch(hosts=["http://localhost:9200"])
    init_indices()
```

---

## 📝 Best Practices

### 1. **Sempre configurar no startup**
```python
from app.models.opensearch import configure_opensearch

@app.on_event("startup")
async def startup():
    configure_opensearch(
        hosts=[settings.opensearch_url],
        use_ssl=False,
        verify_certs=False
    )
```

### 2. **Use métodos helper para busca**
```python
# Bom: método helper
results = BIMElementEmbedding.search_by_vector(query_vec)

# Evite: query manual
search = BIMElementEmbedding.search()
search.update_from_dict({...})  # Complexo
```

### 3. **Timestamps automáticos**
```python
# O método save() já atualiza updated_at
doc.description = "New description"
doc.save()  # updated_at = agora (automático!)
```

### 4. **Bulk para múltiplos docs**
```python
# Para > 10 documentos, use bulk
from opensearch_dsl import bulk

actions = [doc.to_dict(include_meta=True) for doc in docs]
bulk(client, actions)
```

---

## 🔧 Troubleshooting

### Erro: "Connection refused"
```bash
# Verificar se OpenSearch está rodando
docker-compose ps opensearch
curl http://localhost:9200
```

### Erro: "Index already exists"
```python
# Deletar e recriar
from app.models.opensearch import delete_indices, init_indices

delete_indices()  # Cuidado!
init_indices()
```

### Performance lenta em KNN
```python
# Aumentar ef_search nas configurações
class Index:
    settings = {
        "index": {
            "knn": True,
            "knn.algo_param.ef_search": 512  # Aumentar
        }
    }
```

---

## 📚 Referências

- [OpenSearch-DSL Docs](https://opensearch-py.readthedocs.io/en/latest/dsl.html)
- [OpenSearch KNN](https://opensearch.org/docs/latest/search-plugins/knn/index/)
- [Vector Search Guide](https://opensearch.org/docs/latest/search-plugins/knn/approximate-knn/)

---

**✅ OpenSearch com DSL configurado para busca vetorial e semântica!**
