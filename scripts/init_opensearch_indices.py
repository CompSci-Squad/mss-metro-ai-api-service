"""
Script para criar índices OpenSearch com DSL.
Configura índices para embeddings e busca vetorial.
"""

import os

from app.models.opensearch import (
    BIMElementEmbedding,
    ImageAnalysisDocument,
    configure_opensearch,
)


def create_indices():
    """Cria índices OpenSearch para VIRAG-BIM."""
    # Configurar conexão
    host = os.getenv("OPENSEARCH_HOST", "localhost")
    port = os.getenv("OPENSEARCH_PORT", "9200")
    opensearch_url = f"http://{host}:{port}"

    print(f"🔧 Configurando OpenSearch: {opensearch_url}\n")

    configure_opensearch(
        hosts=[opensearch_url],
        use_ssl=False,
        verify_certs=False,
        ssl_show_warn=False,
    )

    # Lista de índices/documentos
    indices = [
        (BIMElementEmbedding, "bim_element_embeddings", "Embeddings de Elementos BIM"),
        (ImageAnalysisDocument, "construction_analyses", "Análises de Imagens"),
    ]

    print("📦 Criando índices OpenSearch...\n")

    for doc_class, index_name, description in indices:
        try:
            index = doc_class._index

            if not index.exists():
                print(f"⏳ Criando {index_name} ({description})...")
                index.create()
                print(f"✓ {index_name} criado com sucesso!")

                # Mostrar configuração
                settings = doc_class.Index.settings
                print(f"   • Shards: {settings.get('number_of_shards', 1)}")
                print(f"   • KNN habilitado: {settings.get('index', {}).get('knn', False)}")
            else:
                print(f"⚠️  {index_name} já existe")

        except Exception as e:
            print(f"❌ Erro ao criar {index_name}: {e}")

    print("\n✅ Todos os índices foram processados!")
    print("\n🚀 OpenSearch pronto para busca vetorial!")


if __name__ == "__main__":
    create_indices()
