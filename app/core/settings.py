from pydantic import Field
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # DynamoDB Configuration
    dynamodb_endpoint_url: str = Field("http://localhost:4566", alias="DYNAMODB_ENDPOINT_URL")

    # Redis Configuration
    redis_host: str = Field("localhost", alias="REDIS_HOST")
    redis_port: int = Field(6379, alias="REDIS_PORT")
    redis_db: int = Field(0, alias="REDIS_DB")
    redis_password: str = Field("", alias="REDIS_PASSWORD")
    redis_url: str = Field("redis://localhost:6379/0", alias="REDIS_URL")

    # OpenSearch Configuration
    opensearch_host: str = Field("localhost", alias="OPENSEARCH_HOST")
    opensearch_port: int = Field(9200, alias="OPENSEARCH_PORT")
    opensearch_hosts: list[str] = Field(default_factory=lambda: ["http://localhost:9200"], alias="OPENSEARCH_HOSTS")
    opensearch_use_ssl: bool = Field(False, alias="OPENSEARCH_USE_SSL")
    opensearch_verify_certs: bool = Field(False, alias="OPENSEARCH_VERIFY_CERTS")

    # VLM Model Configuration
    vlm_model_name: str = Field("Salesforce/blip2-opt-2.7b", alias="VLM_MODEL_NAME")
    vlm_model_cache_dir: str = Field("./models", alias="VLM_MODEL_CACHE_DIR")
    embedding_model_name: str = Field("sentence-transformers/clip-ViT-B-32", alias="EMBEDDING_MODEL_NAME")
    use_quantization: bool = Field(True, alias="USE_QUANTIZATION")
    device: str = Field("cpu", alias="DEVICE")

    # Processing Configuration
    max_image_size: int = Field(1024, alias="MAX_IMAGE_SIZE")
    max_file_size_mb: int = Field(50, alias="MAX_FILE_SIZE_MB")
    cache_ttl: int = Field(3600, alias="CACHE_TTL")  # 1 hour in seconds

    # Validation Configuration
    fuzzy_match_threshold: int = Field(80, alias="FUZZY_MATCH_THRESHOLD")

    class Config:
        env_file = ".env"
        extra = "ignore"


def get_settings() -> Settings:
    """Factory function para criar instância de Settings."""
    return Settings()


settings = get_settings()
