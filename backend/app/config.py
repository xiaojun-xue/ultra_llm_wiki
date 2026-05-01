from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Application configuration loaded from environment variables."""

    # App
    app_name: str = "LLM Wiki"
    debug: bool = False
    api_key: str = "changeme"

    # Database
    database_url: str = "postgresql+asyncpg://llm_wiki:llm_wiki@localhost:5432/llm_wiki"

    # Redis
    redis_url: str = "redis://localhost:6379/0"

    # MinIO / S3
    minio_endpoint: str = "localhost:9000"
    minio_access_key: str = "minioadmin"
    minio_secret_key: str = "minioadmin"
    minio_bucket: str = "wiki-files"
    minio_use_ssl: bool = False

    # Ollama (Embedding)
    ollama_base_url: str = "http://localhost:11434"
    embedding_model: str = "bge-m3"
    embedding_dim: int = 1024

    # MCP Server
    mcp_port: int = 8001

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}


settings = Settings()
