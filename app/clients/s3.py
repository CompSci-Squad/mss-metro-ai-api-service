"""\nCliente S3 completo para VIRAG-BIM.\nUpload, download, listagem e gestão de arquivos.\n"""

import os

import aioboto3
import structlog
from botocore.exceptions import ClientError

logger = structlog.get_logger(__name__)


class S3Client:
    """Cliente S3 com interface completa."""

    def __init__(self, bucket_name: str, endpoint_url: str | None = None):
        self.bucket_name = bucket_name
        self.endpoint_url = endpoint_url
        
        # Configura credenciais AWS (lê de variáveis de ambiente)
        aws_access_key = os.getenv("AWS_ACCESS_KEY_ID", "test")
        aws_secret_key = os.getenv("AWS_SECRET_ACCESS_KEY", "test")
        aws_region = os.getenv("AWS_DEFAULT_REGION", "us-east-1")
        
        self.session = aioboto3.Session(
            aws_access_key_id=aws_access_key,
            aws_secret_access_key=aws_secret_key,
            region_name=aws_region,
        )

    async def ensure_bucket_exists(self) -> None:
        """Garante que o bucket existe, criando se necessário."""
        try:
            async with self.session.client("s3", endpoint_url=self.endpoint_url) as s3:
                try:
                    await s3.head_bucket(Bucket=self.bucket_name)
                    logger.info("bucket_existe", bucket=self.bucket_name)
                except ClientError as e:
                    error_code = e.response.get("Error", {}).get("Code")
                    if error_code == "404":
                        # Bucket não existe, criar
                        await s3.create_bucket(Bucket=self.bucket_name)
                        logger.info("bucket_criado", bucket=self.bucket_name)
                    else:
                        raise
        except Exception as e:
            logger.error("erro_verificar_bucket", error=str(e))
            raise

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
            # Garante que bucket existe
            await self.ensure_bucket_exists()
            
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
                response = await s3.list_objects_v2(Bucket=self.bucket_name, Prefix=prefix, MaxKeys=max_keys)

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

    async def generate_presigned_url(self, s3_key: str, expiration: int = 3600, method: str = "get_object") -> str:
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
