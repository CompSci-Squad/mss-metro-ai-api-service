from datetime import datetime
from enum import Enum

from pydantic import BaseModel, Field


class ProgressStatus(str, Enum):
    NOT_STARTED = "not_started"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    DELAYED = "delayed"
    DEVIATED = "deviated"


class AlertSeverity(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class AlertType(str, Enum):
    DELAY = "delay"
    DEVIATION = "deviation"
    QUALITY_ISSUE = "quality_issue"
    SAFETY_CONCERN = "safety_concern"
    MISSING_ELEMENT = "missing_element"


class IFCElement(BaseModel):
    """Representa um elemento do modelo IFC."""

    element_id: str = Field(..., description="ID único do elemento IFC (GlobalId)")
    element_type: str = Field(..., description="Tipo (Wall, Slab, Column, etc.)")
    name: str | None = Field(None, description="Nome do elemento")
    properties: dict[str, str | int | float] = Field(default_factory=dict, description="Propriedades do elemento")
    geometry: dict[str, bool] | None = Field(None, description="Informações geométricas")
    scheduled_date: datetime | None = Field(None, description="Data prevista de execução")


class IFCUploadRequest(BaseModel):
    """Request para upload de arquivo IFC."""

    project_name: str = Field(..., description="Nome do projeto")
    description: str | None = Field(None, description="Descrição do projeto")
    location: str | None = Field(None, description="Localização da obra")


class IFCUploadResponse(BaseModel):
    """Response do upload de IFC."""

    project_id: str = Field(..., description="ID único do projeto")
    project_name: str = Field(..., description="Nome do projeto")
    s3_key: str = Field(..., description="Chave do arquivo no S3")
    total_elements: int = Field(..., description="Total de elementos processados")
    processing_time: float = Field(..., description="Tempo de processamento em segundos")
    message: str = Field(default="IFC processado com sucesso")


class BIMProject(BaseModel):
    """Schema completo de um projeto BIM."""

    project_id: str
    project_name: str
    description: str | None = None
    location: str | None = None
    ifc_s3_key: str
    total_elements: int
    elements: list[IFCElement] = Field(default_factory=list)
    created_at: datetime
    updated_at: datetime


class AnalysisRequest(BaseModel):
    """Request para análise de imagem da obra."""

    project_id: str = Field(..., description="ID do projeto BIM")
    element_ids: list[str] | None = Field(None, description="IDs específicos de elementos para análise")
    context: str | None = Field(None, description="Contexto adicional (localização, fase)")
    capture_date: datetime | None = Field(None, description="Data de captura da imagem")


class DetectedElement(BaseModel):
    """Elemento detectado na imagem."""

    element_id: str | None = Field(None, description="ID do elemento BIM correspondente")
    element_type: str = Field(..., description="Tipo do elemento detectado")
    confidence: float = Field(..., ge=0.0, le=1.0, description="Confiança da detecção (0-1)")
    status: ProgressStatus = Field(..., description="Status do elemento")
    description: str = Field(..., description="Descrição do que foi detectado")
    deviation: str | None = Field(None, description="Desvio identificado")


class ElementChange(BaseModel):
    """Representa mudança em um elemento entre análises."""

    element_id: str = Field(..., description="ID do elemento")
    element_type: str = Field(..., description="Tipo do elemento")
    change_type: str = Field(..., description="Tipo de mudança: 'new', 'removed', 'progress', 'status_change'")
    previous_status: ProgressStatus | None = Field(None, description="Status anterior")
    current_status: ProgressStatus | None = Field(None, description="Status atual")
    description: str = Field(..., description="Descrição da mudança")


class AnalysisComparison(BaseModel):
    """Comparação entre análise atual e anterior."""

    previous_analysis_id: str = Field(..., description="ID da análise anterior")
    previous_timestamp: datetime = Field(..., description="Data da análise anterior")
    progress_change: float = Field(..., description="Mudança percentual no progresso")
    elements_added: list[ElementChange] = Field(default_factory=list, description="Elementos novos")
    elements_removed: list[ElementChange] = Field(default_factory=list, description="Elementos removidos")
    elements_changed: list[ElementChange] = Field(default_factory=list, description="Elementos com mudança de status")
    summary: str = Field(..., description="Resumo da comparação gerado pela VLM")


class ConstructionAnalysis(BaseModel):
    """Resultado da análise de uma imagem de obra."""

    analysis_id: str = Field(..., description="ID único da análise")
    project_id: str = Field(..., description="ID do projeto")
    image_s3_key: str = Field(..., description="Chave da imagem no S3")
    image_description: str | None = Field(None, description="Descrição da imagem fornecida pelo usuário")
    detected_elements: list[DetectedElement] = Field(default_factory=list, description="Elementos detectados")
    overall_progress: float = Field(..., ge=0.0, le=100.0, description="Progresso geral (%)")
    summary: str = Field(..., description="Resumo textual da análise")
    alerts: list[str] = Field(default_factory=list, description="Alertas identificados")
    comparison: AnalysisComparison | None = Field(None, description="Comparação com análise anterior")
    analyzed_at: datetime = Field(default_factory=datetime.utcnow)
    processing_time: float = Field(..., description="Tempo de processamento em segundos")


class AnalysisResponse(BaseModel):
    """Response da requisição de análise."""

    analysis_id: str
    status: str = Field(default="completed", description="Status da análise")
    result: ConstructionAnalysis
    message: str = Field(default="Análise concluída com sucesso")


class Alert(BaseModel):
    """Schema de um alerta."""

    alert_id: str = Field(..., description="ID único do alerta")
    project_id: str = Field(..., description="ID do projeto")
    analysis_id: str | None = Field(None, description="ID da análise que gerou o alerta")
    alert_type: AlertType = Field(..., description="Tipo do alerta")
    severity: AlertSeverity = Field(..., description="Severidade do alerta")
    title: str = Field(..., description="Título do alerta")
    description: str = Field(..., description="Descrição detalhada")
    element_id: str | None = Field(None, description="ID do elemento afetado")
    created_at: datetime = Field(default_factory=datetime.utcnow)
    resolved: bool = Field(default=False, description="Se o alerta foi resolvido")
    resolved_at: datetime | None = Field(None)
    resolved_by: str | None = Field(None, description="Usuário que resolveu")


class ProjectProgress(BaseModel):
    """Response com progresso e histórico de um projeto."""

    project_id: str
    project_name: str
    total_analyses: int
    analyses: list[ConstructionAnalysis]
    open_alerts: int
    recent_alerts: list[Alert] = Field(default_factory=list)
    overall_progress: float = Field(description="Progresso médio geral do projeto")
    last_analysis_date: datetime | None = None


class AlertListResponse(BaseModel):
    """Response para listagem de alertas."""

    project_id: str
    total_alerts: int
    open_alerts: int
    resolved_alerts: int
    alerts: list[Alert]


class AnalysisListResponse(BaseModel):
    """Response para listagem de análises/relatórios."""

    project_id: str
    project_name: str
    total_reports: int
    reports: list[ConstructionAnalysis]
    latest_progress: float | None = None
