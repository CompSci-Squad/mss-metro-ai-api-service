"""Rotas de análise de imagens da obra."""

from typing import Annotated

import structlog
from dependency_injector.wiring import Provide, inject
from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from pynamodb.exceptions import DoesNotExist
from ulid import ULID

from app.clients.s3 import S3Client
from app.core.container import Container
from app.core.settings import get_settings
from app.core.validators import validate_file_extension, validate_file_size, validate_ulid
from app.models.dynamodb import BIMProject, ConstructionAnalysisModel
from app.schemas.bim import AnalysisResponse, ConstructionAnalysis
from app.services.bim_analysis import BIMAnalysisService

from .utils import save_alerts

router = APIRouter()
logger = structlog.get_logger(__name__)


@router.post("/analyze", response_model=AnalysisResponse, status_code=status.HTTP_200_OK)
@inject
async def analyze_construction_image(
    file: Annotated[UploadFile, File(description="Imagem da obra para análise")],
    project_id: Annotated[str, Form(description="ID do projeto BIM")],
    image_description: Annotated[str | None, Form(description="Descrição da imagem (ex: fachada, estrutura)")] = None,
    context: Annotated[str | None, Form(description="Contexto adicional")] = None,
    s3_client: S3Client = Depends(Provide[Container.s3_client]),
    bim_service: BIMAnalysisService = Depends(Provide[Container.bim_analysis_service]),
):
    """Analisa imagem da obra."""
    try:
        settings = get_settings()

        # Validações
        validate_ulid(project_id)
        validate_file_extension(file.filename or "", [".jpg", ".jpeg", ".png", ".bmp", ".tiff"])
        image_bytes = await validate_file_size(file, settings.max_file_size_mb)

        logger.info("analise_iniciada", project_id=project_id, filename=file.filename)

        # Busca projeto usando ORM
        try:
            project = BIMProject.get(project_id)
        except DoesNotExist:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Projeto não encontrado") from None

        # Converte para dict para compatibilidade
        project_data = {
            "project_id": project.project_id,
            "project_name": project.project_name,
            "total_elements": project.total_elements,
            "elements": project.elements,
        }

        # ID da análise
        analysis_id = str(ULID())

        # Upload imagem
        image_s3_key = f"bim-projects/{project_id}/images/{analysis_id}.jpg"
        await s3_client.upload_file(image_bytes, image_s3_key, content_type="image/jpeg")

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
                image_s3_key=image_s3_key,
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
            image_s3_key=image_s3_key,
            image_description=image_description,
            detected_elements=analysis_result["detected_elements"],
            overall_progress=analysis_result["overall_progress"],
            summary=analysis_result["summary"],
            alerts=analysis_result["alerts"],
            comparison=comparison_data,
            processing_time=analysis_result["processing_time"],
        )

        # Salva análise usando ORM
        analysis_model = ConstructionAnalysisModel(
            analysis_id=analysis_id,
            project_id=project_id,
            image_s3_key=image_s3_key,
            image_description=image_description,
            overall_progress=analysis_result["overall_progress"],
            summary=analysis_result["summary"],
            detected_elements=analysis_result["detected_elements"],
            alerts=analysis_result["alerts"],
            comparison=analysis_result.get("comparison"),
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
