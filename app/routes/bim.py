"""
Rotas da API para VIRAG-BIM usando ORMs (PynamoDB + OpenSearch-DSL).
Endpoints para upload de IFC, análise de imagens e consulta de resultados.
"""

import time
from typing import Annotated

import structlog
from dependency_injector.wiring import Provide, inject
from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from pynamodb.exceptions import DoesNotExist
from ulid import ULID

from app.clients.s3 import S3Client
from app.core.container import Container
from app.models.dynamodb import AlertModel, BIMProject, ConstructionAnalysisModel
from app.schemas.bim import AlertSeverity, AlertType, AnalysisResponse, ConstructionAnalysis, IFCUploadResponse
from app.services.bim_analysis import BIMAnalysisService
from app.services.embedding_service import EmbeddingService
from app.services.ifc_processor import IFCProcessorService
from app.services.vlm_service import VLMService

router = APIRouter(prefix="/bim", tags=["VIRAG-BIM"])
logger = structlog.get_logger(__name__)


# ==================== Upload de IFC ====================


@router.post("/upload-ifc", response_model=IFCUploadResponse, status_code=status.HTTP_201_CREATED)
@inject
async def upload_ifc_file(
    file: Annotated[UploadFile, File(description="Arquivo IFC do modelo BIM")],
    project_name: Annotated[str, Form(description="Nome do projeto")],
    description: Annotated[str | None, Form(description="Descrição do projeto")] = None,
    location: Annotated[str | None, Form(description="Localização da obra")] = None,
    s3_client: S3Client = Depends(Provide[Container.s3_client]),
    embedding_service: EmbeddingService = Depends(Provide[Container.embedding_service]),
):
    """
    Upload e processamento de arquivo IFC usando PynamoDB ORM.

    Processa o modelo BIM, extrai elementos e armazena no DynamoDB.
    """
    try:
        start_time = time.time()

        # Valida extensão
        if not file.filename or not file.filename.lower().endswith(".ifc"):
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Arquivo deve ter extensão .ifc")

        logger.info("upload_ifc_iniciado", filename=file.filename, project_name=project_name)

        # Lê conteúdo
        file_content = await file.read()

        # Processa IFC
        ifc_processor = IFCProcessorService(embedding_service=embedding_service)
        processed_data = await ifc_processor.process_ifc_file(file_content)

        # Gera ID do projeto
        project_id = str(ULID())

        # Upload para S3
        s3_key = f"bim-projects/{project_id}/model.ifc"
        await s3_client.upload_file(file_content, s3_key, content_type="application/x-step")

        # Salva no DynamoDB usando ORM
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
        project.save()  # ORM save!

        # Indexa embeddings no OpenSearch (ass\u00edncrono)
        indexed_count = await ifc_processor.index_elements_to_opensearch(
            project_id=project_id, elements=processed_data["elements"]
        )

        logger.info("embeddings_indexados", count=indexed_count)

        processing_time = time.time() - start_time

        logger.info(
            "upload_ifc_concluido", project_id=project_id, total_elements=processed_data["total_elements"], processing_time=processing_time
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


# ==================== Análise de Imagem ====================


@router.post("/analyze", response_model=AnalysisResponse, status_code=status.HTTP_200_OK)
@inject
async def analyze_construction_image(
    file: Annotated[UploadFile, File(description="Imagem da obra para análise")],
    project_id: Annotated[str, Form(description="ID do projeto BIM")],
    context: Annotated[str | None, Form(description="Contexto adicional")] = None,
    s3_client: S3Client = Depends(Provide[Container.s3_client]),
    vlm_service: VLMService = Depends(Provide[Container.vlm_service]),
    embedding_service: EmbeddingService = Depends(Provide[Container.embedding_service]),
):
    """
    Analisa imagem da obra usando PynamoDB ORM.

    Utiliza VLM para identificar elementos, progresso e desvios.
    """
    try:
        # Valida extensão
        if not file.filename:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Arquivo inválido")

        valid_extensions = [".jpg", ".jpeg", ".png", ".bmp", ".tiff"]
        if not any(file.filename.lower().endswith(ext) for ext in valid_extensions):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST, detail=f"Formato não suportado. Use: {', '.join(valid_extensions)}"
            )

        logger.info("analise_iniciada", project_id=project_id, filename=file.filename)

        # Busca projeto usando ORM
        try:
            project = BIMProject.get(project_id)
        except DoesNotExist:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Projeto não encontrado")

        # Converte para dict para compatibilidade
        project_data = {
            "project_id": project.project_id,
            "project_name": project.project_name,
            "total_elements": project.total_elements,
            "elements": project.elements,
        }

        # Lê imagem
        image_bytes = await file.read()

        # ID da análise
        analysis_id = str(ULID())

        # Upload imagem
        image_s3_key = f"bim-projects/{project_id}/images/{analysis_id}.jpg"
        await s3_client.upload_file(image_bytes, image_s3_key, content_type="image/jpeg")

        # Executa análise
        bim_service = BIMAnalysisService(vlm_service, embedding_service)
        analysis_result = await bim_service.analyze_construction_image(image_bytes=image_bytes, project_data=project_data, context=context)

        # Monta resultado
        result = ConstructionAnalysis(
            analysis_id=analysis_id,
            project_id=project_id,
            image_s3_key=image_s3_key,
            detected_elements=analysis_result["detected_elements"],
            overall_progress=analysis_result["overall_progress"],
            summary=analysis_result["summary"],
            alerts=analysis_result["alerts"],
            processing_time=analysis_result["processing_time"],
        )

        # Salva análise usando ORM
        analysis_model = ConstructionAnalysisModel(
            analysis_id=analysis_id,
            project_id=project_id,
            image_s3_key=image_s3_key,
            overall_progress=analysis_result["overall_progress"],
            summary=analysis_result["summary"],
            detected_elements=analysis_result["detected_elements"],
            alerts=analysis_result["alerts"],
            processing_time=analysis_result["processing_time"],
        )
        analysis_model.save()  # ORM save!

        # Cria alertas se necessário
        if result.alerts:
            for alert_text in result.alerts:
                alert = AlertModel(
                    alert_id=str(ULID()),
                    project_id=project_id,
                    analysis_id=analysis_id,
                    alert_type=AlertType.MISSING_ELEMENT.value,
                    severity=AlertSeverity.MEDIUM.value,
                    title="Elemento não detectado",
                    description=alert_text,
                )
                alert.save()  # ORM save!

        logger.info("analise_concluida", analysis_id=analysis_id, progress=result.overall_progress, alerts=len(result.alerts))

        return AnalysisResponse(analysis_id=analysis_id, result=result)

    except HTTPException:
        raise
    except Exception as e:
        logger.error("erro_analise", error=str(e), exc_info=True)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e)) from e


# ==================== Consulta de Resultados ====================


@router.get("/progress/{project_id}")
@inject
async def get_project_progress(project_id: str):
    """
    Retorna progresso e histórico usando PynamoDB ORM.
    """
    try:
        logger.info("consultando_progresso", project_id=project_id)

        # Busca projeto usando ORM
        try:
            project = BIMProject.get(project_id)
        except DoesNotExist:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Projeto não encontrado")

        # Busca análises usando scan com filtro
        analyses = list(ConstructionAnalysisModel.scan(ConstructionAnalysisModel.project_id == project_id))

        # Busca alertas não resolvidos
        alerts = list(
            AlertModel.scan((AlertModel.project_id == project_id) & ~AlertModel.resolved)
        )

        # Calcula progresso médio
        overall_progress = sum(a.overall_progress for a in analyses) / len(analyses) if analyses else 0.0

        # Última análise
        last_analysis_date = max((a.analyzed_at for a in analyses), default=None) if analyses else None

        return {
            "project_id": project.project_id,
            "project_name": project.project_name,
            "total_analyses": len(analyses),
            "analyses": [
                {
                    "analysis_id": a.analysis_id,
                    "overall_progress": a.overall_progress,
                    "summary": a.summary,
                    "analyzed_at": a.analyzed_at.isoformat() if a.analyzed_at else None,
                }
                for a in analyses
            ],
            "open_alerts": len(alerts),
            "recent_alerts": [
                {
                    "alert_id": alert.alert_id,
                    "alert_type": alert.alert_type,
                    "severity": alert.severity,
                    "title": alert.title,
                    "description": alert.description,
                    "created_at": alert.created_at.isoformat() if alert.created_at else None,
                }
                for alert in alerts[:10]
            ],
            "overall_progress": round(overall_progress, 2),
            "last_analysis_date": last_analysis_date.isoformat() if last_analysis_date else None,
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error("erro_consultar_progresso", error=str(e), exc_info=True)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e)) from e


@router.get("/timeline/{project_id}")
@inject
async def get_project_timeline(project_id: str):
    """
    Retorna timeline cronol\u00f3gica do projeto com visualiza\u00e7\u00e3o de progresso.
    """
    try:
        logger.info("consultando_timeline", project_id=project_id)

        # Busca projeto
        try:
            project = BIMProject.get(project_id)
        except DoesNotExist:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Projeto n\u00e3o encontrado")

        # Busca todas as an\u00e1lises ordenadas por data
        analyses = list(ConstructionAnalysisModel.scan(ConstructionAnalysisModel.project_id == project_id))
        analyses.sort(key=lambda x: x.analyzed_at)

        # Monta timeline
        timeline = []
        for analysis in analyses:
            timeline.append(
                {
                    "timestamp": analysis.analyzed_at.isoformat() if analysis.analyzed_at else None,
                    "analysis_id": analysis.analysis_id,
                    "progress": analysis.overall_progress,
                    "summary": analysis.summary,
                    "image_url": f"s3://{analysis.image_s3_key}",
                    "detected_elements_count": len(analysis.detected_elements),
                    "alerts_count": len(analysis.alerts),
                }
            )

        # Estat\u00edsticas de progresso ao longo do tempo
        progress_evolution = []
        for i, analysis in enumerate(analyses):
            progress_evolution.append(
                {"index": i + 1, "date": analysis.analyzed_at.isoformat(), "progress": analysis.overall_progress}
            )

        # Velocidade de progresso (se houver 2+ an\u00e1lises)
        velocity = None
        if len(analyses) >= 2:
            first = analyses[0]
            last = analyses[-1]
            time_diff = (last.analyzed_at - first.analyzed_at).days
            progress_diff = last.overall_progress - first.overall_progress

            if time_diff > 0:
                velocity = round(progress_diff / time_diff, 2)  # % por dia

        return {
            "project_id": project.project_id,
            "project_name": project.project_name,
            "timeline": timeline,
            "progress_evolution": progress_evolution,
            "total_analyses": len(analyses),
            "current_progress": analyses[-1].overall_progress if analyses else 0.0,
            "velocity": velocity,
            "velocity_unit": "% por dia" if velocity else None,
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error("erro_consultar_timeline", error=str(e), exc_info=True)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e)) from e


@router.get("/compare/{project_id}")
@inject
async def compare_analyses(project_id: str, analysis_ids: str):
    """
    Compara m\u00faltiplas an\u00e1lises lado a lado.

    Args:
        project_id: ID do projeto
        analysis_ids: IDs das an\u00e1lises separados por v\u00edrgula (ex: "id1,id2,id3")
    """
    try:
        logger.info("comparando_analises", project_id=project_id, analysis_ids=analysis_ids)

        # Busca projeto
        try:
            project = BIMProject.get(project_id)
        except DoesNotExist:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Projeto n\u00e3o encontrado")

        # Parse IDs
        ids = [aid.strip() for aid in analysis_ids.split(",")]

        # Busca an\u00e1lises
        comparisons = []
        for analysis_id in ids:
            try:
                analysis = ConstructionAnalysisModel.get(analysis_id)

                comparisons.append(
                    {
                        "analysis_id": analysis.analysis_id,
                        "timestamp": analysis.analyzed_at.isoformat() if analysis.analyzed_at else None,
                        "progress": analysis.overall_progress,
                        "summary": analysis.summary,
                        "detected_elements": analysis.detected_elements,
                        "alerts": analysis.alerts,
                    }
                )
            except DoesNotExist:
                logger.warning("analise_nao_encontrada", analysis_id=analysis_id)
                continue

        if not comparisons:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Nenhuma an\u00e1lise encontrada")

        # Ordena por data
        comparisons.sort(key=lambda x: x["timestamp"] if x["timestamp"] else "")

        # Calcula diferen\u00e7as
        differences = []
        if len(comparisons) >= 2:
            for i in range(1, len(comparisons)):
                prev = comparisons[i - 1]
                curr = comparisons[i]

                progress_diff = curr["progress"] - prev["progress"]
                new_alerts = len(curr["alerts"]) - len(prev["alerts"])

                differences.append(
                    {
                        "from": prev["analysis_id"],
                        "to": curr["analysis_id"],
                        "progress_change": round(progress_diff, 2),
                        "new_alerts": new_alerts,
                    }
                )

        return {
            "project_id": project.project_id,
            "project_name": project.project_name,
            "comparisons": comparisons,
            "differences": differences,
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error("erro_comparar_analises", error=str(e), exc_info=True)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e)) from e
