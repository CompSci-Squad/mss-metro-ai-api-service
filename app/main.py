import os

from fastapi import FastAPI

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


@app.on_event("startup")
async def startup_event():
    """Configura ORMs e servi\u00e7os no startup."""
    # Configura PynamoDB (DynamoDB)
    from app.models.dynamodb import configure_models

    dynamodb_endpoint = os.getenv("DYNAMODB_ENDPOINT_URL", "http://localhost:4566")
    configure_models(dynamodb_endpoint)
    print(f"\u2705 PynamoDB configurado: {dynamodb_endpoint}")

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
    print(f"\u2705 OpenSearch-DSL configurado: {opensearch_url}")

    print("\u2705 VIRAG-BIM iniciado com sucesso!")


app.include_router(health.router, tags=["health"])
app.include_router(bim_router)
