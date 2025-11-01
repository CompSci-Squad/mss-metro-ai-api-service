"""\nCliente S3 completo para VIRAG-BIM.\nUpload, download, listagem e gestão de arquivos.\n"""

import aioboto3
import structlog
from botocore.exceptions import ClientError

logger = structlog.get_logger(__name__)


class S3Client:
    """Cliente S3 com interface completa."""

    def __init__(self, bucket_name: str, endpoint_url: str | None = None):
        self.bucket_name = bucket_name
        self.endpoint_url = endpoint_url
        self.session = aioboto3.Session()

    async def upload_file(
        self,
        file_data: bytes,
        s3_key: str,
        content_type: str = "application/octet-stream",
        metadata: dict | None = None,
    ) -> dict:
        """
        Faz upload de arquivo para S3.

        Args:
            file_data: Bytes do arquivo
            s3_key: Chave S3 (caminho)
            content_type: MIME type
            metadata: Metadados customizados

        Returns:
            Dict com informações do upload
        """
        try:
            async with self.session.client("s3", endpoint_url=self.endpoint_url) as s3:
                await s3.put_object(
                    Bucket=self.bucket_name,
                    Key=s3_key,
                    Body=file_data,
                    ContentType=content_type,
                    Metadata=metadata or {},
                )

            logger.info("s3_upload_sucesso", s3_key=s3_key, size=len(file_data))

            return {
                "bucket": self.bucket_name,
                "key": s3_key,
                "size": len(file_data),
                "url": f"s3://{self.bucket_name}/{s3_key}",
            }

        except ClientError as e:
            logger.error("erro_s3_upload", error=str(e), s3_key=s3_key)
            raise

    async def download_file(self, s3_key: str) -> bytes:
        """
        Baixa arquivo do S3.

        Args:
            s3_key: Chave S3 do arquivo

        Returns:
            Bytes do arquivo
        """
        try:
            async with self.session.client("s3", endpoint_url=self.endpoint_url) as s3:
                response = await s3.get_object(Bucket=self.bucket_name, Key=s3_key)
                data = await response["Body"].read()

            logger.info("s3_download_sucesso", s3_key=s3_key, size=len(data))
            return data

        except ClientError as e:
            logger.error("erro_s3_download", error=str(e), s3_key=s3_key)
            raise

    async def delete_file(self, s3_key: str) -> bool:
        """Deleta arquivo do S3."""
        try:
            async with self.session.client("s3", endpoint_url=self.endpoint_url) as s3:
                await s3.delete_object(Bucket=self.bucket_name, Key=s3_key)

            logger.info("s3_delete_sucesso", s3_key=s3_key)
            return True

        except ClientError as e:
            logger.error("erro_s3_delete", error=str(e), s3_key=s3_key)
            return False

    async def list_files(self, prefix: str = "", max_keys: int = 1000) -> list[dict]:
        """Lista arquivos no S3."""
        try:
            async with self.session.client("s3", endpoint_url=self.endpoint_url) as s3:
                response = await s3.list_objects_v2(
                    Bucket=self.bucket_name, Prefix=prefix, MaxKeys=max_keys
                )

            files = []
            for obj in response.get("Contents", []):
                files.append(
                    {
                        "key": obj["Key"],
                        "size": obj["Size"],
                        "last_modified": obj["LastModified"].isoformat(),
                    }
                )

            logger.info("s3_list_sucesso", prefix=prefix, count=len(files))
            return files

        except ClientError as e:
            logger.error("erro_s3_list", error=str(e), prefix=prefix)
            return []

    async def generate_presigned_url(
        self, s3_key: str, expiration: int = 3600, method: str = "get_object"
    ) -> str:
        """Gera URL pré-assinada."""
        try:
            async with self.session.client("s3", endpoint_url=self.endpoint_url) as s3:
                url = await s3.generate_presigned_url(
                    ClientMethod=method,
                    Params={"Bucket": self.bucket_name, "Key": s3_key},
                    ExpiresIn=expiration,
                )

            logger.info("presigned_url_gerada", s3_key=s3_key, expiration=expiration)
            return url

        except ClientError as e:
            logger.error("erro_presigned_url", error=str(e), s3_key=s3_key)
            raise

    async def file_exists(self, s3_key: str) -> bool:
        """Verifica se arquivo existe."""
        try:
            async with self.session.client("s3", endpoint_url=self.endpoint_url) as s3:
                await s3.head_object(Bucket=self.bucket_name, Key=s3_key)
            return True

        except ClientError:
            return False
