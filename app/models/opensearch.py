"""Modelos OpenSearch para armazenamento de embeddings."""

from datetime import datetime

from opensearch_dsl import Date, DenseVector, Document, Keyword, Text, connections

from app.core.settings import settings


class BIMElementEmbedding(Document):
    """
    Documento para embeddings de elementos BIM.
    Permite busca vetorial (KNN) e semântica.
    """

    # IDs e metadados
    element_id = Keyword()
    project_id = Keyword()
    project_description = Text()
    
    # Informações do elemento
    element_type = Keyword()
    element_name = Text()
    description = Text()
    
    # Propriedades adicionais
    properties = Text()
    
    # Embedding vetorial (512 dimensões - CLIP)
    embedding = DenseVector(dims=512)
    
    # Timestamps
    created_at = Date()
    updated_at = Date()

    class Index:
        name = "bim-elements"
        settings = {
            "number_of_shards": 1,
            "number_of_replicas": 0,
            "index": {
                "knn": True,  # Habilita KNN para busca vetorial
                "knn.algo_param.ef_search": 512,
            },
        }

    def save(self, **kwargs):
        """Override save para adicionar timestamp."""
        if not self.created_at:
            self.created_at = datetime.utcnow()
        self.updated_at = datetime.utcnow()
        return super().save(**kwargs)

    @classmethod
    def search_by_vector(cls, query_embedding: list[float], size: int = 10, project_id: str | None = None):
        """
        Busca por similaridade vetorial (KNN).

        Args:
            query_embedding: Vetor de consulta (512 dims)
            size: Número de resultados
            project_id: Filtrar por projeto

        Returns:
            Lista de documentos (dicionários com dados + score)
        """
        # Pega a conexão
        conn = connections.get_connection()
        
        # Monta query KNN conforme documentação oficial OpenSearch 2.x
        # https://docs.opensearch.org/2.19/vector-search/filter-search-knn/efficient-knn-filtering/
        # Sintaxe: query.knn.{field_name}.{vector, k, filter}
        knn_query = {
            "embedding": {
                "vector": query_embedding,
                "k": size
            }
        }
        
        # Adiciona filtro dentro do campo knn se especificado
        if project_id:
            knn_query["embedding"]["filter"] = {
                "term": {"project_id": project_id}
            }
        
        query_body = {
            "size": size,
            "query": {
                "knn": knn_query
            }
        }
        
        # Executa query usando API de baixo nível
        response = conn.search(index="bim-elements", body=query_body)
        
        # Converte hits para objetos simples (não usa from_es)
        results = []
        for hit in response["hits"]["hits"]:
            # Cria objeto simples com dados do documento
            doc_data = hit["_source"].copy()
            doc_data["_score"] = hit.get("_score", 0.0)
            doc_data["_id"] = hit.get("_id")
            
            # Cria mock object com atributos para compatibilidade
            class MockDoc:
                def __init__(self, data):
                    for key, value in data.items():
                        setattr(self, key, value)
                    self.meta = type('obj', (object,), {'score': data.get('_score', 0.0)})()
            
            results.append(MockDoc(doc_data))
        
        return results


class ImageAnalysisDocument(Document):
    """
    Documento para armazenar embeddings de análises de imagens.
    Permite comparação temporal e busca por similaridade.
    """

    # IDs
    analysis_id = Keyword()
    project_id = Keyword()
    
    # Metadados da análise
    image_description = Text()
    overall_progress = Keyword()
    summary = Text()
    
    # Embedding da imagem (512 dimensões - CLIP)
    image_embedding = DenseVector(dims=512)
    
    # Timestamps
    analyzed_at = Date()

    class Index:
        name = "image-analysis"
        settings = {
            "number_of_shards": 1,
            "number_of_replicas": 0,
            "index": {"knn": True},
        }

    @classmethod
    def search_by_vector(cls, query_embedding: list[float], size: int = 10, project_id: str | None = None):
        """
        Busca análises similares por embedding vetorial.

        Args:
            query_embedding: Vetor de consulta (512 dims)
            size: Número de resultados
            project_id: Filtrar por projeto

        Returns:
            Lista de documentos similares
        """
        conn = connections.get_connection()
        
        query_body = {
            "size": size,
            "query": {
                "bool": {
                    "must": [],
                    "filter": []
                }
            }
        }
        
        if project_id:
            query_body["query"]["bool"]["filter"].append({
                "term": {"project_id": project_id}
            })
        
        query_body["query"]["bool"]["must"].append({
            "knn": {
                "image_embedding": {
                    "vector": query_embedding,
                    "k": size
                }
            }
        })
        
        response = conn.search(index="image-analysis", body=query_body)
        
        results = []
        for hit in response["hits"]["hits"]:
            # Cria objeto simples com dados do documento
            doc_data = hit["_source"].copy()
            doc_data["_score"] = hit.get("_score", 0.0)
            doc_data["_id"] = hit.get("_id")
            
            # Cria mock object com atributos
            class MockDoc:
                def __init__(self, data):
                    for key, value in data.items():
                        setattr(self, key, value)
                    self.meta = type('obj', (object,), {'score': data.get('_score', 0.0)})()
            
            results.append(MockDoc(doc_data))
        
        return results


def configure_opensearch(hosts: list[str], use_ssl: bool = False, verify_certs: bool = False, ssl_show_warn: bool = False):
    """
    Configura conexão com OpenSearch usando opensearch-dsl.
    
    Args:
        hosts: Lista de URLs do OpenSearch
        use_ssl: Se deve usar SSL
        verify_certs: Se deve verificar certificados SSL
        ssl_show_warn: Se deve mostrar avisos SSL
    """
    connections.create_connection(
        hosts=hosts,
        use_ssl=use_ssl,
        verify_certs=verify_certs,
        ssl_show_warn=ssl_show_warn,
    )
    
    # Cria índices se não existirem
    try:
        # Inicializa índice de elementos BIM
        if not BIMElementEmbedding._index.exists():
            BIMElementEmbedding.init()
            print("Índice 'bim-elements' criado com sucesso")
        else:
            print("Índice 'bim-elements' já existe")
        
        # Inicializa índice de análises de imagem
        if not ImageAnalysisDocument._index.exists():
            ImageAnalysisDocument.init()
            print("Índice 'image-analysis' criado com sucesso")
        else:
            print("Índice 'image-analysis' já existe")
            
    except Exception as e:
        print(f"Erro ao criar índices OpenSearch: {e}")
        print(f"  Tentando criar índices manualmente...")
        
        # Fallback: tenta criar via API de baixo nível
        try:
            conn = connections.get_connection()
            
            # Cria índice bim-elements se não existir
            if not conn.indices.exists(index="bim-elements"):
                conn.indices.create(
                    index="bim-elements",
                    body={
                        "settings": {
                            "number_of_shards": 1,
                            "number_of_replicas": 0,
                            "index": {"knn": True, "knn.algo_param.ef_search": 512},
                        },
                        "mappings": {
                            "properties": {
                                "element_id": {"type": "keyword"},
                                "project_id": {"type": "keyword"},
                                "project_description": {"type": "text"},
                                "element_type": {"type": "keyword"},
                                "element_name": {"type": "text"},
                                "description": {"type": "text"},
                                "properties": {"type": "text"},
                                "embedding": {
                                    "type": "knn_vector",
                                    "dimension": 512,
                                    "method": {
                                        "name": "hnsw",
                                        "space_type": "cosinesimil",
                                        "engine": "lucene",
                                    },
                                },
                                "created_at": {"type": "date"},
                                "updated_at": {"type": "date"},
                            }
                        },
                    },
                )
                print("Índice 'bim-elements' criado manualmente")
            
            # Cria índice image-analysis se não existir
            if not conn.indices.exists(index="image-analysis"):
                conn.indices.create(
                    index="image-analysis",
                    body={
                        "settings": {
                            "number_of_shards": 1,
                            "number_of_replicas": 0,
                            "index": {"knn": True},
                        },
                        "mappings": {
                            "properties": {
                                "analysis_id": {"type": "keyword"},
                                "project_id": {"type": "keyword"},
                                "image_description": {"type": "text"},
                                "overall_progress": {"type": "keyword"},
                                "summary": {"type": "text"},
                                "image_embedding": {
                                    "type": "knn_vector",
                                    "dimension": 512,
                                    "method": {
                                        "name": "hnsw",
                                        "space_type": "cosinesimil",
                                        "engine": "lucene",
                                    },
                                },
                                "analyzed_at": {"type": "date"},
                            }
                        },
                    },
                )
                print("Índice 'image-analysis' criado manualmente")
                
        except Exception as fallback_error:
            print(f"Erro ao criar índices manualmente: {fallback_error}")


def init_opensearch():
    """Inicializa conexão com OpenSearch usando settings."""
    connections.create_connection(
        hosts=[f"{settings.opensearch_host}:{settings.opensearch_port}"],
        use_ssl=settings.opensearch_use_ssl,
        verify_certs=settings.opensearch_verify_certs,
        ssl_show_warn=False,
    )

    # Cria índices se não existirem
    BIMElementEmbedding.init()
    ImageAnalysisDocument.init()
