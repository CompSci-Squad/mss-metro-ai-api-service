#!/usr/bin/env python3
"""
Limpa todos os dados do OpenSearch e recria índices.
USO COM CUIDADO! Apaga TODOS os dados!
"""

from opensearchpy import OpenSearch
import sys

def confirm_deletion():
    """Pede confirmação antes de deletar"""
    print("=" * 60)
    print("⚠️  ATENÇÃO: OPERAÇÃO DESTRUTIVA!")
    print("=" * 60)
    print("\nEste script vai:")
    print("  1. DELETAR todos os índices do OpenSearch")
    print("  2. Recriar os índices vazios")
    print("\nVocê perderá:")
    print("  - Todos os elementos BIM indexados")
    print("  - Todas as análises de imagens")
    print("  - Todos os embeddings")
    print("\nPara reindexar, você precisará:")
    print("  - Fazer upload do IFC novamente")
    print("  - Refazer as análises")
    print("\n" + "=" * 60)
    
    response = input("\nTem CERTEZA que deseja continuar? Digite 'SIM DELETAR TUDO': ")
    return response == "SIM DELETAR TUDO"

def main():
    if not confirm_deletion():
        print("\n✗ Operação cancelada pelo usuário.")
        sys.exit(0)
    
    print("\n🔧 Conectando ao OpenSearch...")
    
    # Conecta OpenSearch
    client = OpenSearch(
        hosts=[{"host": "localhost", "port": 9200}],
        http_auth=None,
        use_ssl=False,
        verify_certs=False
    )
    
    # Lista índices para deletar
    indices_to_delete = ["bim-elements", "image-analysis"]
    
    print("\n🗑️  Deletando índices...")
    for index_name in indices_to_delete:
        try:
            if client.indices.exists(index=index_name):
                client.indices.delete(index=index_name)
                print(f"  ✓ Deletado: {index_name}")
            else:
                print(f"  - Não existe: {index_name}")
        except Exception as e:
            print(f"  ✗ Erro ao deletar {index_name}: {e}")
    
    print("\n📋 Recriando índices...")
    
    # Recria índice bim-elements
    try:
        bim_elements_mapping = {
            "mappings": {
                "properties": {
                    "element_id": {"type": "keyword"},
                    "project_id": {"type": "keyword"},
                    "project_description": {"type": "text"},
                    "element_type": {"type": "keyword"},
                    "element_name": {"type": "text"},
                    "description": {"type": "text"},
                    "properties": {"type": "object", "enabled": False},
                    "embedding": {
                        "type": "knn_vector",
                        "dimension": 1024,
                        "method": {
                            "name": "hnsw",
                            "space_type": "cosinesimil",
                            "engine": "lucene",
                            "parameters": {
                                "ef_construction": 256,
                                "m": 48
                            }
                        }
                    },
                    "created_at": {"type": "date"},
                    "updated_at": {"type": "date"}
                }
            }
        }
        
        client.indices.create(index="bim-elements", body=bim_elements_mapping)
        print("  ✓ Criado: bim-elements")
    except Exception as e:
        print(f"  ✗ Erro ao criar bim-elements: {e}")
    
    # Recria índice image-analysis
    try:
        image_analysis_mapping = {
            "mappings": {
                "properties": {
                    "analysis_id": {"type": "keyword"},
                    "project_id": {"type": "keyword"},
                    "image_description": {"type": "text"},
                    "embedding": {
                        "type": "knn_vector",
                        "dimension": 1024,
                        "method": {
                            "name": "hnsw",
                            "space_type": "cosinesimil",
                            "engine": "lucene",
                            "parameters": {
                                "ef_construction": 256,
                                "m": 48
                            }
                        }
                    },
                    "analyzed_at": {"type": "date"}
                }
            }
        }
        
        client.indices.create(index="image-analysis", body=image_analysis_mapping)
        print("  ✓ Criado: image-analysis")
    except Exception as e:
        print(f"  ✗ Erro ao criar image-analysis: {e}")
    
    print("\n" + "=" * 60)
    print("✅ OPERAÇÃO CONCLUÍDA!")
    print("=" * 60)
    print("\nPróximos passos:")
    print("  1. Faça upload do arquivo IFC:")
    print("     curl -X POST http://localhost:8000/bim/upload \\")
    print("       -F 'file=@seu_arquivo.ifc' \\")
    print("       -F 'project_id=360' \\")
    print("       -F 'description=Descrição do projeto'")
    print("\n  2. Aguarde o processamento (pode demorar alguns minutos)")
    print("\n  3. Verifique:")
    print("     python scripts/check_opensearch_indices.py")
    print()

if __name__ == "__main__":
    main()
