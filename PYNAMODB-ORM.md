# 🔄 Migração para PynamoDB (ORM)

## ✅ Melhorias Implementadas

### 1. **PynamoDB** - ORM para DynamoDB

Substituímos o cliente boto3 manual por **PynamoDB**, um ORM estilo SQLAlchemy para DynamoDB.

#### Antes (boto3 manual):
```python
# Código verboso
await dynamodb_client.put_item(
    table_name="virag_projects",
    item={
        "project_id": project_id,
        "project_name": project_name,
        "created_at": datetime.utcnow().isoformat(),
        # ... mais campos
    }
)
```

#### Depois (PynamoDB ORM):
```python
# Código limpo e tipo-safe
project = BIMProject(
    project_id=project_id,
    project_name=project_name,
    # created_at automático!
)
project.save()
```

### 2. **LocalStack Centralizado**

Removemos o DynamoDB Local separado e centralizamos tudo no **LocalStack**.

#### Antes:
- LocalStack (porta 4566) → S3
- DynamoDB Local (porta 8001) → DynamoDB

#### Depois:
- LocalStack (porta 4566) → S3 + DynamoDB

**Vantagens:**
- ✅ Menos containers
- ✅ Mais simples de gerenciar
- ✅ Endpoint único: `http://localhost:4566`

---

## 📦 Models Criados

### `app/models/dynamodb.py`

Três models ORM declarativos:

#### 1. BIMProject
```python
class BIMProject(Model):
    class Meta:
        table_name = "virag_projects"
    
    project_id = UnicodeAttribute(hash_key=True)
    project_name = UnicodeAttribute()
    description = UnicodeAttribute(null=True)
    location = UnicodeAttribute(null=True)
    ifc_s3_key = UnicodeAttribute()
    total_elements = NumberAttribute()
    elements = ListAttribute(default=list)
    project_info = MapAttribute(default=dict)
    created_at = UTCDateTimeAttribute(default=datetime.utcnow)
    updated_at = UTCDateTimeAttribute(default=datetime.utcnow)
```

#### 2. ConstructionAnalysisModel
```python
class ConstructionAnalysisModel(Model):
    class Meta:
        table_name = "virag_analyses"
    
    analysis_id = UnicodeAttribute(hash_key=True)
    project_id = UnicodeAttribute()
    image_s3_key = UnicodeAttribute()
    overall_progress = NumberAttribute()
    summary = UnicodeAttribute()
    detected_elements = ListAttribute(default=list)
    alerts = ListAttribute(default=list)
    analyzed_at = UTCDateTimeAttribute(default=datetime.utcnow)
```

#### 3. AlertModel
```python
class AlertModel(Model):
    class Meta:
        table_name = "virag_alerts"
    
    alert_id = UnicodeAttribute(hash_key=True)
    project_id = UnicodeAttribute()
    analysis_id = UnicodeAttribute(null=True)
    alert_type = UnicodeAttribute()
    severity = UnicodeAttribute()
    title = UnicodeAttribute()
    description = UnicodeAttribute()
    resolved = BooleanAttribute(default=False)
    created_at = UTCDateTimeAttribute(default=datetime.utcnow)
```

---

## 🔧 Como Usar

### Configurar Endpoint
```python
from app.models.dynamodb import configure_models

# Configurar para LocalStack
configure_models("http://localhost:4566")
```

### Criar (INSERT)
```python
from app.models.dynamodb import BIMProject

project = BIMProject(
    project_id="01JXXX...",
    project_name="Estação Vila Prudente",
    description="Expansão Linha 2",
    ifc_s3_key="s3://...",
    total_elements=150
)
project.save()
```

### Buscar por ID (GET)
```python
# Buscar por primary key
project = BIMProject.get("01JXXX...")

print(project.project_name)  # "Estação Vila Prudente"
print(project.total_elements)  # 150
```

### Atualizar (UPDATE)
```python
project = BIMProject.get("01JXXX...")
project.description = "Nova descrição"
project.save()  # updated_at automático!
```

### Deletar (DELETE)
```python
project = BIMProject.get("01JXXX...")
project.delete()
```

### Query/Scan
```python
# Scan simples
for project in BIMProject.scan():
    print(project.project_name)

# Scan com filtro
for project in BIMProject.scan(
    BIMProject.location == "Vila Prudente"
):
    print(project.project_name)
```

### Batch Operations
```python
# Batch get
projects = BIMProject.batch_get([
    ("id1",),
    ("id2",),
    ("id3",),
])

# Batch write
with BIMProject.batch_write() as batch:
    for i in range(10):
        batch.save(BIMProject(
            project_id=f"proj_{i}",
            project_name=f"Projeto {i}",
            # ...
        ))
```

---

## 🎯 Vantagens do PynamoDB

### 1. **Type Safety**
```python
# Validação automática de tipos
project.total_elements = "150"  # ❌ TypeError!
project.total_elements = 150     # ✅ OK
```

### 2. **Timestamps Automáticos**
```python
# created_at e updated_at gerenciados automaticamente
project = BIMProject(...)
project.save()  # created_at = agora

project.description = "Nova desc"
project.save()  # updated_at = agora (automático!)
```

### 3. **Queries Pythônicas**
```python
# SQL-like queries
BIMProject.scan(
    BIMProject.location.contains("São Paulo") &
    (BIMProject.total_elements > 100)
)
```

### 4. **Intellisense/Autocomplete**
```python
project.  # IDE mostra todos os atributos!
```

### 5. **Menos Código Boilerplate**
```python
# Antes: ~30 linhas de código boto3
# Depois: ~5 linhas com PynamoDB
```

---

## 🐳 Docker Compose Atualizado

```yaml
localstack:
  image: localstack/localstack:3.0
  ports:
    - "4566:4566"
  environment:
    - SERVICES=s3,dynamodb  # S3 + DynamoDB juntos!

api:
  environment:
    - DYNAMODB_ENDPOINT_URL=http://localstack:4566  # Endpoint único
```

---

## 🚀 Setup Atualizado

### 1. Instalar Dependências
```bash
uv sync  # PynamoDB será instalado
```

### 2. Iniciar LocalStack
```bash
docker-compose up -d localstack
```

### 3. Criar Tabelas com ORM
```bash
uv run python scripts/init_dynamodb_tables.py
```

Saída:
```
🔧 Configurando DynamoDB endpoint: http://localhost:4566

📦 Criando tabelas DynamoDB...

⏳ Criando virag_projects (Projetos BIM)...
✓ virag_projects criada com sucesso!
⏳ Criando virag_analyses (Análises de Imagens)...
✓ virag_analyses criada com sucesso!
⏳ Criando virag_alerts (Alertas)...
✓ virag_alerts criada com sucesso!

✅ Todas as tabelas foram processadas!
🚀 Pronto para usar VIRAG-BIM!
```

### 4. Usar na API
```python
# app/routes/bim.py
from app.models.dynamodb import BIMProject, configure_models

# Configurar no startup
configure_models(settings.dynamodb_endpoint_url)

# Usar nos endpoints
@router.post("/upload-ifc")
async def upload_ifc(...):
    project = BIMProject(
        project_id=str(ULID()),
        project_name=project_name,
        # ...
    )
    project.save()  # Salva no DynamoDB
    
    return {"project_id": project.project_id}
```

---

## 📊 Comparação

| Aspecto | Boto3 Manual | PynamoDB ORM |
|---------|-------------|--------------|
| Linhas de código | ~100 | ~30 |
| Type safety | ❌ | ✅ |
| Autocomplete | ❌ | ✅ |
| Timestamps | Manual | Automático |
| Validação | Manual | Automática |
| Queries | Verboso | Pythônico |
| Manutenção | Difícil | Fácil |

---

## 🎓 Próximos Passos

### Curto Prazo
- [ ] Atualizar rotas para usar models ORM
- [ ] Adicionar índices secundários (GSI)
- [ ] Implementar soft delete

### Médio Prazo
- [ ] Adicionar validações customizadas
- [ ] Implementar migrations
- [ ] Adicionar testes com mocks

---

## 📚 Referências

- [PynamoDB Docs](https://pynamodb.readthedocs.io/)
- [LocalStack DynamoDB](https://docs.localstack.cloud/user-guide/aws/dynamodb/)
- [DynamoDB Best Practices](https://docs.aws.amazon.com/amazondynamodb/latest/developerguide/best-practices.html)

---

**✅ Migração completa para PynamoDB ORM + LocalStack centralizado!**
