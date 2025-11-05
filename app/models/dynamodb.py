"""
Models PynamoDB para DynamoDB (ORM estilo SQLAlchemy).
Define estrutura das tabelas de forma declarativa.
"""

from datetime import datetime

from pynamodb.attributes import (
    BooleanAttribute,
    ListAttribute,
    MapAttribute,
    NumberAttribute,
    UnicodeAttribute,
    UTCDateTimeAttribute,
)
from pynamodb.indexes import GlobalSecondaryIndex, AllProjection
from pynamodb.models import Model


class BIMProject(Model):
    """
    Tabela de projetos BIM.
    ORM mapping para virag_projects.
    """

    class Meta:
        table_name = "virag_projects"
        region = "us-east-1"
        host = None  # Será configurado dinamicamente

    # Primary Key
    project_id = UnicodeAttribute(hash_key=True)

    # Attributes
    project_name = UnicodeAttribute()
    description = UnicodeAttribute(null=True)
    location = UnicodeAttribute(null=True)
    ifc_s3_key = UnicodeAttribute()
    total_elements = NumberAttribute()

    # JSON/Map attributes
    elements = ListAttribute(default=list)
    project_info = MapAttribute(default=dict)

    # Timestamps
    created_at = UTCDateTimeAttribute(default=datetime.utcnow)
    updated_at = UTCDateTimeAttribute(default=datetime.utcnow)

    def save(self, *args, **kwargs):
        """Override save to update timestamp."""
        self.updated_at = datetime.utcnow()
        super().save(*args, **kwargs)


class ProjectIdIndex(GlobalSecondaryIndex):
    """Índice secundário para query por project_id."""

    class Meta:
        index_name = "project_id_index"
        projection = AllProjection()
        read_capacity_units = 1
        write_capacity_units = 1

    project_id = UnicodeAttribute(hash_key=True)
    analyzed_at = UnicodeAttribute(range_key=True)


class ConstructionAnalysisModel(Model):
    """
    Tabela de análises de imagens.
    ORM mapping para virag_analyses.
    """

    class Meta:
        table_name = "virag_analyses"
        region = "us-east-1"
        host = None

    # Primary Key
    analysis_id = UnicodeAttribute(hash_key=True)

    # Attributes
    project_id = UnicodeAttribute()
    image_s3_key = UnicodeAttribute()
    image_description = UnicodeAttribute(null=True)  # Descrição fornecida pelo usuário
    overall_progress = NumberAttribute()
    summary = UnicodeAttribute()

    # JSON attributes
    detected_elements = ListAttribute(default=list)
    alerts = ListAttribute(default=list)
    comparison = MapAttribute(null=True)  # Comparação com análise anterior

    # Timestamp
    analyzed_at = UTCDateTimeAttribute(default=datetime.utcnow)

    # Índice para query por projeto
    project_id_index = ProjectIdIndex()


class AlertProjectIdIndex(GlobalSecondaryIndex):
    """Índice secundário para query de alertas por project_id."""

    class Meta:
        index_name = "project_id_index"
        projection = AllProjection()
        read_capacity_units = 1
        write_capacity_units = 1

    project_id = UnicodeAttribute(hash_key=True)
    created_at = UnicodeAttribute(range_key=True)


class AlertModel(Model):
    """
    Tabela de alertas.
    ORM mapping para virag_alerts.
    """

    class Meta:
        table_name = "virag_alerts"
        region = "us-east-1"
        host = None

    # Primary Key
    alert_id = UnicodeAttribute(hash_key=True)

    # Attributes
    project_id = UnicodeAttribute()
    analysis_id = UnicodeAttribute(null=True)
    alert_type = UnicodeAttribute()
    severity = UnicodeAttribute()
    title = UnicodeAttribute()
    description = UnicodeAttribute()
    element_id = UnicodeAttribute(null=True)

    # Status
    resolved = BooleanAttribute(default=False)
    resolved_at = UTCDateTimeAttribute(null=True)
    resolved_by = UnicodeAttribute(null=True)

    # Timestamp
    created_at = UTCDateTimeAttribute(default=datetime.utcnow)

    # Índice para query por projeto
    project_id_index = AlertProjectIdIndex()


def configure_models(endpoint_url: str):
    """
    Configura endpoint para todos os models.
    Permite usar LocalStack ou DynamoDB real.

    Args:
        endpoint_url: URL do DynamoDB (LocalStack ou AWS)
    """
    BIMProject.Meta.host = endpoint_url
    ConstructionAnalysisModel.Meta.host = endpoint_url
    AlertModel.Meta.host = endpoint_url


def create_tables_if_not_exist():
    """
    Cria todas as tabelas se não existirem.
    Útil para desenvolvimento/testes.
    """
    tables = [BIMProject, ConstructionAnalysisModel, AlertModel]

    for table in tables:
        if not table.exists():
            table.create_table(
                read_capacity_units=1,
                write_capacity_units=1,
                wait=True,
            )
            print(f"✓ Tabela {table.Meta.table_name} criada")
        else:
            print(f"⚠ Tabela {table.Meta.table_name} já existe")
