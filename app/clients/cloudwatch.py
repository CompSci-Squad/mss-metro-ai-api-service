"""
Cliente CloudWatch Logs para VIRAG-BIM.
Envia logs estruturados para CloudWatch (LocalStack).
"""

import asyncio
from datetime import datetime

import aioboto3
import structlog
from botocore.exceptions import ClientError

logger = structlog.get_logger(__name__)


class CloudWatchLogsClient:
    """Cliente para enviar logs estruturados ao CloudWatch."""

    def __init__(self, log_group: str = "/virag-bim/api", endpoint_url: str | None = None):
        self.log_group = log_group
        self.endpoint_url = endpoint_url
        self.session = aioboto3.Session()
        self._sequence_tokens = {}

    async def _ensure_log_group(self, client) -> None:
        """Garante que o log group existe."""
        try:
            await client.create_log_group(logGroupName=self.log_group)
            logger.info("cloudwatch_log_group_criado", log_group=self.log_group)
        except ClientError as e:
            if e.response["Error"]["Code"] != "ResourceAlreadyExistsException":
                raise

    async def _ensure_log_stream(self, client, stream_name: str) -> None:
        """Garante que o log stream existe."""
        try:
            await client.create_log_stream(
                logGroupName=self.log_group,
                logStreamName=stream_name,
            )
            logger.info("cloudwatch_log_stream_criado", stream=stream_name)
        except ClientError as e:
            if e.response["Error"]["Code"] != "ResourceAlreadyExistsException":
                raise

    async def send_log(
        self,
        message: str,
        stream_name: str = "default",
        level: str = "INFO",
        metadata: dict | None = None,
    ) -> bool:
        """
        Envia log para CloudWatch.

        Args:
            message: Mensagem do log
            stream_name: Nome do stream (ex: project_id, analysis_id)
            level: Nível do log
            metadata: Metadados adicionais

        Returns:
            True se enviado com sucesso
        """
        try:
            async with self.session.client("logs", endpoint_url=self.endpoint_url) as client:
                await self._ensure_log_group(client)
                await self._ensure_log_stream(client, stream_name)

                # Monta mensagem estruturada
                log_entry = {
                    "timestamp": int(datetime.utcnow().timestamp() * 1000),
                    "message": f"[{level}] {message}",
                }

                if metadata:
                    log_entry["message"] += f" | {metadata}"

                # Envia log
                params = {
                    "logGroupName": self.log_group,
                    "logStreamName": stream_name,
                    "logEvents": [log_entry],
                }

                # Adiciona sequence token se existir
                if stream_name in self._sequence_tokens:
                    params["sequenceToken"] = self._sequence_tokens[stream_name]

                response = await client.put_log_events(**params)

                # Atualiza sequence token
                if "nextSequenceToken" in response:
                    self._sequence_tokens[stream_name] = response["nextSequenceToken"]

                return True

        except Exception as e:
            logger.error("erro_enviar_cloudwatch", error=str(e), stream=stream_name)
            return False

    async def send_batch_logs(
        self,
        logs: list[dict],
        stream_name: str = "default",
    ) -> int:
        """
        Envia múltiplos logs em batch.

        Args:
            logs: Lista de logs [{message, level, metadata}]
            stream_name: Nome do stream

        Returns:
            Número de logs enviados
        """
        try:
            async with self.session.client("logs", endpoint_url=self.endpoint_url) as client:
                await self._ensure_log_group(client)
                await self._ensure_log_stream(client, stream_name)

                log_events = []
                for log in logs:
                    log_entry = {
                        "timestamp": int(datetime.utcnow().timestamp() * 1000),
                        "message": f"[{log.get('level', 'INFO')}] {log['message']}",
                    }
                    if log.get("metadata"):
                        log_entry["message"] += f" | {log['metadata']}"
                    log_events.append(log_entry)

                params = {
                    "logGroupName": self.log_group,
                    "logStreamName": stream_name,
                    "logEvents": log_events,
                }

                if stream_name in self._sequence_tokens:
                    params["sequenceToken"] = self._sequence_tokens[stream_name]

                response = await client.put_log_events(**params)

                if "nextSequenceToken" in response:
                    self._sequence_tokens[stream_name] = response["nextSequenceToken"]

                logger.info("cloudwatch_batch_enviado", count=len(log_events), stream=stream_name)
                return len(log_events)

        except Exception as e:
            logger.error("erro_batch_cloudwatch", error=str(e))
            return 0

    async def query_logs(
        self,
        query: str,
        start_time: datetime,
        end_time: datetime,
        limit: int = 100,
    ) -> list[dict]:
        """
        Consulta logs usando CloudWatch Insights.

        Args:
            query: Query string (ex: "fields @timestamp, @message | filter level = 'ERROR'")
            start_time: Data início
            end_time: Data fim
            limit: Limite de resultados

        Returns:
            Lista de resultados
        """
        try:
            async with self.session.client("logs", endpoint_url=self.endpoint_url) as client:
                response = await client.start_query(
                    logGroupName=self.log_group,
                    startTime=int(start_time.timestamp()),
                    endTime=int(end_time.timestamp()),
                    queryString=query,
                    limit=limit,
                )

                query_id = response["queryId"]

                # Aguarda query completar
                while True:
                    result = await client.get_query_results(queryId=query_id)
                    status = result["status"]

                    if status == "Complete":
                        return result.get("results", [])
                    elif status == "Failed":
                        raise Exception(f"Query falhou: {result.get('statistics')}")

                    await asyncio.sleep(0.5)

        except Exception as e:
            logger.error("erro_query_cloudwatch", error=str(e))
            return []
