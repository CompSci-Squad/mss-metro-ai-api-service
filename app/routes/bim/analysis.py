"""Rotas de análise de imagens da obra."""

from typing import Annotated

import structlog
from dependency_injector.wiring import Provide, inject
from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from ulid import ULID

from app.core.container import Container
from app.core.settings import get_settings
from app.core.validators import validate_file_extension
from app.models.dynamodb import ConstructionAnalysisModel
from app.schemas.bim import AnalysisResponse, ConstructionAnalysis
from app.services.bim_analysis import BIMAnalysisService

from .utils import save_alerts

router = APIRouter()
logger = structlog.get_logger(__name__)


@router.post(
    "/analyze",
    response_model=AnalysisResponse,
    status_code=status.HTTP_200_OK,
    tags=["Análise"],
    summary="Análise de imagem da obra",
    responses={
        200: {
            "description": "Análise concluída com sucesso",
            "content": {
                "application/json": {
                    "example": {
                        "analysis_id": "01HXYZ456DEF",
                        "status": "completed",
                        "message": "Análise concluída com sucesso",
                        "result": {
                            "analysis_id": "01HXYZ456DEF",
                            "project_id": "01HXYZ123ABC",
                            "image_s3_key": "bim-projects/01HXYZ123ABC/images/01HXYZ456DEF.jpg",
                            "image_description": "Estrutura de concreto - pilares e vigas",
                            "detected_elements": [
                                {
                                    "element_id": "2O2Fr$t4X7Zf8NOew3FLOH",
                                    "element_type": "IfcColumn",
                                    "confidence": 0.89,
                                    "status": "completed",
                                    "description": "Pilar de concreto detectado com alta confiança",
                                    "deviation": None
                                },
                                {
                                    "element_id": "3P3Gs$u5Y8Ag9OPfx4GMPI",
                                    "element_type": "IfcBeam",
                                    "confidence": 0.76,
                                    "status": "in_progress",
                                    "description": "Viga parcialmente construída",
                                    "deviation": None
                                }
                            ],
                            "overall_progress": 67.5,
                            "summary": "A imagem mostra 3 pilares de concreto completos e 2 vigas em andamento. A estrutura está 67% concluída.",
                            "alerts": [
                                "IfcWall (Parede Norte) não identificado na imagem"
                            ],
                            "comparison": {
                                "previous_analysis_id": "01HXYZ789GHI",
                                "previous_timestamp": "2024-11-05T10:30:00Z",
                                "progress_change": 12.5,
                                "elements_added": [],
                                "elements_removed": [],
                                "elements_changed": [
                                    {
                                        "element_id": "3P3Gs$u5Y8Ag9OPfx4GMPI",
                                        "element_type": "IfcBeam",
                                        "change_type": "status_change",
                                        "previous_status": "not_started",
                                        "current_status": "in_progress",
                                        "description": "Status alterado de not_started para in_progress"
                                    }
                                ],
                                "summary": "Progresso de 12.5% desde a última análise. Viga iniciada."
                            },
                            "analyzed_at": "2024-11-07T14:20:00Z",
                            "processing_time": 12.34
                        }
                    }
                }
            }
        },
        400: {
            "description": "Erro de validação",
            "content": {
                "application/json": {
                    "examples": {
                        "invalid_format": {
                            "summary": "Formato de imagem inválido",
                            "value": {"detail": "Arquivo deve ser JPG, PNG, BMP ou TIFF"}
                        },
                        "file_too_large": {
                            "summary": "Arquivo muito grande",
                            "value": {"detail": "Imagem excede o tamanho máximo de 100MB"}
                        },
                        "invalid_project_id": {
                            "summary": "ID de projeto inválido",
                            "value": {"detail": "project_id deve ser um ULID válido"}
                        }
                    }
                }
            }
        },
        404: {
            "description": "Projeto não encontrado",
            "content": {
                "application/json": {
                    "example": {"detail": "Projeto não encontrado"}
                }
            }
        },
        500: {
            "description": "Erro interno no processamento da análise",
            "content": {
                "application/json": {
                    "example": {"detail": "Erro ao gerar embedding da imagem"}
                }
            }
        }
    }
)
@inject
async def analyze_construction_image(
    file: Annotated[UploadFile, File(description="Imagem da obra (JPG, PNG, BMP, TIFF - máx 100MB)")],
    project_id: Annotated[str, Form(description="ID do projeto BIM (ULID)")],
    image_description: Annotated[str, Form(description="Descrição da imagem (ex: 'Fachada principal', 'Estrutura 2º andar')")],
    context: Annotated[str | None, Form(description="Contexto adicional para melhorar precisão da análise")] = None,
    bim_service: BIMAnalysisService = Depends(Provide[Container.bim_analysis_service]),
):
    """Analisa imagem da obra usando VI-RAG (Vision + RAG + BIM)."""
    try:
        settings = get_settings()

        # Validações
        validate_file_extension(file.filename or "", [".jpg", ".jpeg", ".png", ".bmp", ".tiff"])
        image_bytes = await file.read()

        logger.info("analise_iniciada", project_id=project_id, filename=file.filename)

        # Busca total de elementos do projeto no OpenSearch
        from opensearch_dsl import connections
        
        try:
            conn = connections.get_connection()
            count_response = conn.count(
                index="bim-elements",
                body={"query": {"term": {"project_id": project_id}}}
            )
            total_elements = count_response.get("count", 0)
            logger.info("total_elements_found", project_id=project_id, total=total_elements)
        except Exception as e:
            logger.warning("erro_ao_contar_elementos", error=str(e))
            total_elements = 0
        
        # Dados do projeto
        project_data = {
            "project_id": project_id,
            "project_name": "Unknown",
            "total_elements": total_elements,
            "elements": [],  # Lista completa não necessária para cálculo
        }

        # ID da análise
        analysis_id = str(ULID())

        # Executa análise VI-RAG completa
        analysis_result = await bim_service.analyze_construction_image(
            image_bytes=image_bytes,
            project_data=project_data,
            image_description=image_description,
            context=context,
        )

        # Salva embedding da imagem no OpenSearch
        try:
            from datetime import datetime

            from app.models.opensearch import ImageAnalysisDocument

            img_doc = ImageAnalysisDocument(
                analysis_id=analysis_id,
                project_id=project_id,
                image_description=image_description or "",
                overall_progress=str(analysis_result["overall_progress"]),
                summary=analysis_result["summary"],
                image_embedding=analysis_result["image_embedding"],
                analyzed_at=datetime.utcnow(),
            )
            img_doc.save()
            logger.info("embedding_imagem_salvo", analysis_id=analysis_id)
        except Exception as e:
            logger.warning("erro_salvar_embedding_imagem", error=str(e))

        # Monta resultado com comparação
        comparison_data = None
        if analysis_result.get("comparison"):
            from app.schemas.bim import AnalysisComparison

            comparison_data = AnalysisComparison(**analysis_result["comparison"])

        result = ConstructionAnalysis(
            analysis_id=analysis_id,
            project_id=project_id,
            image_description=image_description,
            detected_elements=analysis_result["detected_elements"],
            overall_progress=analysis_result["overall_progress"],
            summary=analysis_result["summary"],
            alerts=analysis_result["alerts"],
            comparison=comparison_data,
            processing_time=analysis_result["processing_time"],
        )

        # Serializa elementos para DynamoDB (converte enums para string)
        def serialize_for_dynamodb(obj):
            """Converte enums e outros tipos não suportados pelo DynamoDB."""
            if isinstance(obj, dict):
                return {k: serialize_for_dynamodb(v) for k, v in obj.items()}
            elif isinstance(obj, list):
                return [serialize_for_dynamodb(item) for item in obj]
            elif hasattr(obj, "value"):  # Enum
                return obj.value
            return obj

        # Salva análise no DynamoDB
        analysis_model = ConstructionAnalysisModel(
            analysis_id=analysis_id,
            project_id=project_id,
            image_description=image_description,
            overall_progress=analysis_result["overall_progress"],
            summary=analysis_result["summary"],
            detected_elements=serialize_for_dynamodb(analysis_result["detected_elements"]),
            alerts=serialize_for_dynamodb(analysis_result["alerts"]),
            comparison=serialize_for_dynamodb(analysis_result.get("comparison")),
        )
        analysis_model.save()

        # Cria alertas estruturados se necessário
        if result.alerts:
            await save_alerts(
                project_id=project_id,
                analysis_id=analysis_id,
                alerts_text=result.alerts,
            )

        logger.info(
            "analise_concluida", analysis_id=analysis_id, progress=result.overall_progress, alerts=len(result.alerts)
        )

        return AnalysisResponse(analysis_id=analysis_id, result=result)

    except HTTPException:
        raise
    except Exception as e:
        logger.error("erro_analise", error=str(e), exc_info=True)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e)) from e
