"""
Models OpenSearch-DSL para embeddings e busca vetorial.
Define documentos de forma declarativa (ORM-style).
"""

from datetime import datetime

from opensearch_dsl import Date, DenseVector, Document, Keyword, Text, connections


class BIMElementEmbedding(Document):
    """
    Documento para embeddings de elementos BIM.
    Permite busca vetorial (KNN) e semântica.
    """

    # IDs e metadados
    element_id = Keyword(required=True)
    project_id = Keyword(required=True)
    element_type = Keyword(required=True)

    # Descrição textual
    description = Text(analyzer="standard")
    element_name = Text(analyzer="standard")

    # Properties como texto para busca
    properties_text = Text(analyzer="standard")

    # Embedding vetorial (512 dimensões para CLIP)
    embedding = DenseVector(dims=512)

    # Timestamps
    created_at = Date(default_timezone="UTC")
    updated_at = Date(default_timezone="UTC")

    class Index:
        """Configuração do índice."""

        name = "bim_element_embeddings"
        settings = {
            "number_of_shards": 1,
            "number_of_replicas": 0,
            "index": {
                "knn": True,  # Habilita KNN para busca vetorial
                "knn.algo_param.ef_search": 512,
            },
        }

    def save(self, **kwargs):
        """Override save para atualizar timestamp."""
        self.updated_at = datetime.utcnow()
        if not self.created_at:
            self.created_at = datetime.utcnow()
        return super().save(**kwargs)

    @classmethod
    def search_by_vector(cls, query_embedding: list[float], size: int = 10, project_id: str | None = None):
        """
        Busca por similaridade vetorial (KNN).

        Args:
            query_embedding: Vetor de consulta (512 dims)
            size: Número de resultados
            project_id: Filtrar por projeto (opcional)

        Returns:
            Search object configurado
        """
        search = cls.search()

        # Query KNN
        knn_query = {
            "knn": {
                "embedding": {
                    "vector": query_embedding,
                    "k": size,
                }
            }
        }

        search = search.update_from_dict({"query": knn_query})

        # Filtro por projeto se especificado
        if project_id:
            search = search.filter("term", project_id=project_id)

        return search[:size]

    @classmethod
    def search_by_text(cls, query_text: str, size: int = 10, project_id: str | None = None):
        """
        Busca textual (full-text search).

        Args:
            query_text: Texto de busca
            size: Número de resultados
            project_id: Filtrar por projeto

        Returns:
            Search object configurado
        """
        search = cls.search()

        # Multi-match em campos de texto
        search = search.query(
            "multi_match",
            query=query_text,
            fields=["description", "element_name", "properties_text"],
            fuzziness="AUTO",
        )

        if project_id:
            search = search.filter("term", project_id=project_id)

        return search[:size]

    def to_dict_with_score(self, score: float = None):
        """Retorna dict do documento com score opcional."""
        doc = self.to_dict()
        if score is not None:
            doc["_score"] = score
        return doc


class ImageAnalysisDocument(Document):
    """
    Documento para análises de imagens.
    Armazena metadados e embeddings de imagens analisadas.
    """

    # IDs
    analysis_id = Keyword(required=True)
    project_id = Keyword(required=True)
    image_s3_key = Keyword(required=True)

    # Metadados da análise
    image_description = Text(analyzer="standard")  # Descrição fornecida pelo usuário (metadado)
    overall_progress = Text()
    summary = Text(analyzer="standard")

    # Embedding da imagem (para busca visual)
    image_embedding = DenseVector(dims=512)

    # Timestamp
    analyzed_at = Date(default_timezone="UTC")

    class Index:
        name = "construction_analyses"
        settings = {
            "number_of_shards": 1,
            "number_of_replicas": 0,
            "index": {"knn": True},
        }

    @classmethod
    def search_similar_images(cls, query_embedding: list[float], size: int = 5, project_id: str | None = None):
        """
        Busca imagens similares usando embedding.

        Args:
            query_embedding: Vetor da imagem de consulta
            size: Número de resultados
            project_id: Filtrar por projeto

        Returns:
            Search results
        """
        search = cls.search()

        knn_query = {"knn": {"image_embedding": {"vector": query_embedding, "k": size}}}

        search = search.update_from_dict({"query": knn_query})

        if project_id:
            search = search.filter("term", project_id=project_id)

        return search[:size]


def configure_opensearch(hosts: list[str] | str, **kwargs):
    """
    Configura conexão global do OpenSearch-DSL.

    Args:
        hosts: Lista de hosts OpenSearch ou string única
        **kwargs: Argumentos adicionais (use_ssl, verify_certs, etc.)
    """
    if isinstance(hosts, str):
        hosts = [hosts]

    connections.create_connection(
        alias="default",
        hosts=hosts,
        **kwargs,
    )


def init_indices():
    """
    Cria índices se não existirem.
    Safe para executar múltiplas vezes.
    """
    indices = [BIMElementEmbedding, ImageAnalysisDocument]

    for doc_class in indices:
        index = doc_class._index
        if not index.exists():
            index.create()
            print(f"✓ Índice {index._name} criado")
        else:
            print(f"⚠️  Índice {index._name} já existe")


def delete_indices():
    """
    Deleta todos os índices (usar com cuidado!).
    Útil para desenvolvimento/testes.
    """
    indices = [BIMElementEmbedding, ImageAnalysisDocument]

    for doc_class in indices:
        index = doc_class._index
        if index.exists():
            index.delete()
            print(f"✓ Índice {index._name} deletado")
