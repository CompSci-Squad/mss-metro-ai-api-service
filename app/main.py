import os

from dotenv import load_dotenv
from fastapi import FastAPI

# Carrega .env ANTES de tudo
load_dotenv()

from app.core.container import Container
from app.routes import health
from app.routes.bim import router as bim_router

# Inicializa container DI
container = Container()
container.wire(modules=[__name__])

app = FastAPI(
    title="VIRAG-BIM - Sistema de Monitoramento de Obras",
    description="Sistema automatizado de monitoramento de obras usando BIM e VLM",
    version="1.0.0",
)

app.container = container  # type: ignore

# Estado dos modelos ML (usado pelo healthcheck)
app.state.ml_models_loaded = False
app.state.vlm_service = None
app.state.embedding_service = None


@app.on_event("startup")
async def startup_event():
    """Configura ORMs e serviços no startup."""
    # Configura PynamoDB (DynamoDB)
    from app.models.dynamodb import (
        AlertModel,
        BIMProject,
        ConstructionAnalysisModel,
        configure_models,
    )

    dynamodb_endpoint = os.getenv("DYNAMODB_ENDPOINT_URL", "http://localhost:4566")
    configure_models(dynamodb_endpoint)
    print(f"PynamoDB configurado: {dynamodb_endpoint}")
    
    # Auto-cria tabelas se não existirem
    tables = [
        (BIMProject, "virag_projects"),
        (ConstructionAnalysisModel, "virag_analyses"),
        (AlertModel, "virag_alerts"),
    ]
    
    for model, table_name in tables:
        try:
            if not model.exists():
                print(f"Criando tabela {table_name}...")
                model.create_table(
                    read_capacity_units=5,
                    write_capacity_units=5,
                    wait=True,
                )
                print(f"Tabela {table_name} criada!")
            else:
                print(f"Tabela {table_name} já existe")
        except Exception as e:
            print(f"Erro ao verificar/criar {table_name}: {e}")

    # Configura OpenSearch-DSL
    from app.models.opensearch import configure_opensearch

    opensearch_host = os.getenv("OPENSEARCH_HOST", "localhost")
    opensearch_port = os.getenv("OPENSEARCH_PORT", "9200")
    opensearch_url = f"http://{opensearch_host}:{opensearch_port}"

    configure_opensearch(
        hosts=[opensearch_url],
        use_ssl=False,
        verify_certs=False,
        ssl_show_warn=False,
    )
    print(f"OpenSearch-DSL configurado: {opensearch_url}")

    # ========================================
    # PRELOAD ML MODELS (Eager Loading)
    # ========================================
    print("\nCarregando modelos ML...")

    try:
        # 1. Carrega VLM (Vision-Language Model)
        print("Carregando VLM (BLIP2)...")
        from app.services.vlm_service import VLMService
        app.state.vlm_service = VLMService()
        print("VLM carregado e pronto!")

        # 2. Carrega Embedding Service (CLIP)
        print("Carregando Embedding Service (CLIP)...")
        from app.services.embedding_service import EmbeddingService
        app.state.embedding_service = EmbeddingService()
        print("Embedding Service carregado e pronto!")

        # Marca como carregado
        app.state.ml_models_loaded = True

        print("\nTodos os modelos ML carregados com sucesso!")
        print("Sistema pronto para receber requisições!")

    except Exception as e:
        print(f"\nERRO ao carregar modelos ML: {e}")
        print("O servidor iniciará, mas análises podem falhar!")
        app.state.ml_models_loaded = False
        import traceback
        traceback.print_exc()

    print("\nVIRAG-BIM iniciado com sucesso!")


app.include_router(health.router, tags=["health"])
app.include_router(bim_router)
