# 🚀 Quick Start - VIRAG-BIM

Guia de 5 minutos para começar a usar o VIRAG-BIM.

## ⚡ Início Rápido

### 1. Instalar Dependências (30s)

```bash
cd mss-metro-ai-api-service
uv sync
```

### 2. Iniciar Serviços (1min)

```bash
docker-compose up -d
# Aguarde ~30s para os serviços iniciarem
```

### 3. Criar Tabelas (10s)

```bash
uv run python scripts/init_dynamodb_tables.py
```

### 4. Iniciar API (5s)

```bash
uv run task dev
```

### 5. Testar (2min)

Acesse: http://localhost:8000/docs

## 📝 Workflow Básico

### Passo 1: Upload IFC

```bash
curl -X POST "http://localhost:8000/bim/upload-ifc" \
  -F "file=@seu-modelo.ifc" \
  -F "project_name=Meu Projeto"
```

**Guarde o `project_id` retornado!**

### Passo 2: Analisar Imagem

```bash
curl -X POST "http://localhost:8000/bim/analyze" \
  -F "file=@foto-obra.jpg" \
  -F "project_id=SEU_PROJECT_ID"
```

### Passo 3: Ver Progresso

```bash
curl "http://localhost:8000/bim/progress/SEU_PROJECT_ID"
```

## 🐍 Testando com Python

```python
import requests

API = "http://localhost:8000"

# 1. Upload IFC
with open("modelo.ifc", "rb") as f:
    resp = requests.post(f"{API}/bim/upload-ifc",
        files={"file": f},
        data={"project_name": "Teste"})
    project_id = resp.json()["project_id"]

# 2. Analisar imagem
with open("foto.jpg", "rb") as f:
    resp = requests.post(f"{API}/bim/analyze",
        files={"file": f},
        data={"project_id": project_id})
    print(f"Progresso: {resp.json()['result']['overall_progress']}%")

# 3. Ver resultados
resp = requests.get(f"{API}/bim/progress/{project_id}")
print(f"Total análises: {resp.json()['total_analyses']}")
```

## 🔧 Comandos Essenciais

```bash
# Iniciar API
uv run task dev

# Ver logs
docker-compose logs -f

# Reiniciar tudo
docker-compose restart

# Parar tudo
docker-compose down

# Rodar testes
uv run task test

# Formatar código
uv run task lint-fix
```

## 🎯 Estrutura de Dados

### IFC Upload Response
```json
{
  "project_id": "01JXXX...",
  "total_elements": 150,
  "s3_key": "bim-projects/.../model.ifc"
}
```

### Analysis Response
```json
{
  "analysis_id": "01JYYY...",
  "result": {
    "overall_progress": 45.5,
    "detected_elements": [...],
    "alerts": [...]
  }
}
```

## ⚠️ Troubleshooting Rápido

| Problema | Solução |
|----------|---------|
| Porta 8000 ocupada | `kill -9 $(lsof -ti:8000)` |
| DynamoDB não conecta | `docker-compose restart dynamodb` |
| Modelo lento | Use GPU: `DEVICE=cuda` no .env |
| Import error | `uv sync` |

## 📊 Próximos Passos

1. ✅ Testar com seus arquivos IFC reais
2. ✅ Ajustar configurações no `.env`
3. ✅ Explorar endpoints na documentação `/docs`
4. ✅ Implementar autenticação (se necessário)
5. ✅ Configurar monitoramento

## 🆘 Ajuda

- 📖 README completo: `VIRAG-BIM-README.md`
- 🔧 Ver logs: `docker-compose logs -f api`
- 🐛 Issues: Abra uma issue no GitHub

---

**Happy Coding!** 🚀🏗️
