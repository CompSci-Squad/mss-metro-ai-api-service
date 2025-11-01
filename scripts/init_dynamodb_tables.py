"""
Script para criar tabelas DynamoDB com PynamoDB (ORM).
Cria tabelas no LocalStack para VIRAG-BIM.
"""

import os

from app.models.dynamodb import (
    AlertModel,
    BIMProject,
    ConstructionAnalysisModel,
    configure_models,
)


def create_tables():
    """Cria as tabelas no DynamoDB (LocalStack)."""
    # Configura endpoint do LocalStack
    endpoint = os.getenv("DYNAMODB_ENDPOINT_URL", "http://localhost:4566")
    print(f"🔧 Configurando DynamoDB endpoint: {endpoint}\n")

    configure_models(endpoint)

    # Lista de models/tabelas
    tables = [
        (BIMProject, "virag_projects", "Projetos BIM"),
        (ConstructionAnalysisModel, "virag_analyses", "Análises de Imagens"),
        (AlertModel, "virag_alerts", "Alertas"),
    ]

    print("📦 Criando tabelas DynamoDB...\n")

    for model, table_name, description in tables:
        try:
            if not model.exists():
                print(f"⏳ Criando {table_name} ({description})...")
                model.create_table(
                    read_capacity_units=5,
                    write_capacity_units=5,
                    wait=True,
                )
                print(f"✓ {table_name} criada com sucesso!")
            else:
                print(f"⚠️  {table_name} já existe")
        except Exception as e:
            print(f"❌ Erro ao criar {table_name}: {e}")

    print("\n✅ Todas as tabelas foram processadas!")
    print("\n🚀 Pronto para usar VIRAG-BIM!")


if __name__ == "__main__":
    create_tables()
