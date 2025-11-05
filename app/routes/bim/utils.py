"""Utilitários compartilhados entre rotas BIM."""

import structlog
from ulid import ULID

from app.models.dynamodb import AlertModel
from app.schemas.bim import AlertSeverity, AlertType

logger = structlog.get_logger(__name__)


async def save_alerts(project_id: str, analysis_id: str, alerts_text: list[str]) -> int:
    """Salva alertas estruturados no DynamoDB."""
    saved_count = 0

    for alert_text in alerts_text:
        try:
            alert_type = AlertType.DEVIATION
            severity = AlertSeverity.MEDIUM

            text_lower = alert_text.lower()

            if any(word in text_lower for word in ["missing", "faltando", "ausente", "não detectado"]):
                alert_type = AlertType.MISSING_ELEMENT
            elif any(word in text_lower for word in ["delay", "atraso", "atrasado"]):
                alert_type = AlertType.DELAY
            elif any(word in text_lower for word in ["quality", "qualidade", "defeito"]):
                alert_type = AlertType.QUALITY_ISSUE
            elif any(word in text_lower for word in ["safety", "segurança", "risco"]):
                alert_type = AlertType.SAFETY_CONCERN
                severity = AlertSeverity.HIGH

            if any(word in text_lower for word in ["critical", "crítico", "urgente", "grave"]):
                severity = AlertSeverity.CRITICAL
            elif any(word in text_lower for word in ["high", "alto", "importante"]):
                severity = AlertSeverity.HIGH
            elif any(word in text_lower for word in ["low", "baixo", "menor"]):
                severity = AlertSeverity.LOW

            alert = AlertModel(
                alert_id=str(ULID()),
                project_id=project_id,
                analysis_id=analysis_id,
                alert_type=alert_type.value,
                severity=severity.value,
                title=f"{alert_type.value.replace('_', ' ').title()} detectado",
                description=alert_text,
            )
            alert.save()
            saved_count += 1

        except Exception as e:
            logger.warning("erro_salvar_alerta", error=str(e), alert_text=alert_text)
            continue

    logger.info("alertas_salvos", count=saved_count)
    return saved_count
