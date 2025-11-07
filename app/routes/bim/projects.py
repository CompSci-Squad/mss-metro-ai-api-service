"""Rotas de gerenciamento de projetos BIM."""

import time
from typing import Annotated

import structlog
from dependency_injector.wiring import Provide, inject
from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from ulid import ULID

from app.clients.s3 import S3Client
from app.core.container import Container
from app.core.settings import get_settings
from app.core.validators import validate_file_extension, validate_file_size, validate_project_name
from app.models.dynamodb import BIMProject
from app.schemas.bim import IFCUploadResponse
from app.services.ifc_processor import IFCProcessorService

router = APIRouter()
logger = structlog.get_logger(__name__)


@router.post(
    "/upload-ifc",
    response_model=IFCUploadResponse,
    status_code=status.HTTP_201_CREATED,
    tags=["Projetos"],
    summary="Upload de arquivo IFC",
    responses={
        201: {
            "description": "IFC processado com sucesso",
            "content": {
                "application/json": {
                    "example": {
                        "project_id": "01HXYZ123ABC",
                        "project_name": "Edifício Residencial ABC",
                        "s3_key": "bim-projects/01HXYZ123ABC/model.ifc",
                        "total_elements": 245,
                        "processing_time": 18.45,
                        "message": "IFC processado com sucesso"
                    }
                }
            }
        },
        400: {
            "description": "Erro de validação (arquivo inválido, nome do projeto inválido)",
            "content": {
                "application/json": {
                    "examples": {
                        "invalid_extension": {
                            "summary": "Extensão inválida",
                            "value": {"detail": "Arquivo deve ter extensão .ifc"}
                        },
                        "file_too_large": {
                            "summary": "Arquivo muito grande",
                            "value": {"detail": "Arquivo excede o tamanho máximo de 100MB"}
                        },
                        "invalid_project_name": {
                            "summary": "Nome de projeto inválido",
                            "value": {"detail": "Nome do projeto deve ter entre 3 e 100 caracteres"}
                        }
                    }
                }
            }
        },
        500: {
            "description": "Erro interno no processamento do IFC",
            "content": {
                "application/json": {
                    "example": {"detail": "Erro ao processar arquivo IFC: formato corrompido"}
                }
            }
        }
    }
)
@inject
async def upload_ifc_file(
    file: Annotated[UploadFile, File(description="Arquivo IFC do modelo BIM (máx 100MB, formato .ifc)")],
    project_name: Annotated[str, Form(description="Nome do projeto (3-100 caracteres)", min_length=3, max_length=100)],
    description: Annotated[str | None, Form(description="Descrição opcional do projeto")] = None,
    location: Annotated[str | None, Form(description="Localização da obra (endereço, cidade)")] = None,
    s3_client: S3Client = Depends(Provide[Container.s3_client]),
    ifc_processor: IFCProcessorService = Depends(Provide[Container.ifc_processor]),
):
    """Upload e processamento completo de arquivo IFC."""
    try:
        start_time = time.time()
        settings = get_settings()

        validate_file_extension(file.filename or "", [".ifc"])
        validate_project_name(project_name)
        file_content = await validate_file_size(file, settings.max_file_size_mb)

        logger.info("upload_ifc_iniciado", filename=file.filename, project_name=project_name)

        processed_data = await ifc_processor.process_ifc_file(file_content)
        project_id = str(ULID())

        s3_key = f"bim-projects/{project_id}/model.ifc"
        await s3_client.upload_file(file_content, s3_key, content_type="application/x-step")
        project = BIMProject(
            project_id=project_id,
            project_name=project_name,
            description=description,
            location=location,
            ifc_s3_key=s3_key,
            total_elements=processed_data["total_elements"],
            elements=processed_data["elements"],
            project_info=processed_data["project_info"],
        )
        project.save()

        indexed_count = await ifc_processor.index_elements_to_opensearch(
            project_id=project_id, elements=processed_data["elements"]
        )

        logger.info("embeddings_indexados", count=indexed_count)

        processing_time = time.time() - start_time

        logger.info(
            "upload_ifc_concluido",
            project_id=project_id,
            total_elements=processed_data["total_elements"],
            processing_time=processing_time,
        )

        return IFCUploadResponse(
            project_id=project_id,
            project_name=project_name,
            s3_key=s3_key,
            total_elements=processed_data["total_elements"],
            processing_time=round(processing_time, 2),
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error("erro_upload_ifc", error=str(e), exc_info=True)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e)) from e
