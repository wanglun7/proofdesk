from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    postgres_dsn: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/proofdesk"
    openai_api_key: str = ""
    openai_base_url: str = "https://api.openai.com/v1"
    openai_model: str = "gpt-4o"
    dashscope_api_key: str = ""
    dashscope_base_url: str = "https://dashscope-intl.aliyuncs.com/api/v1"
    embedding_model: str = "text-embedding-v4"
    reranker_model: str = "qwen3-rerank"
    embed_dim: int = 1024
    # Auth
    admin_username: str = "admin"
    admin_password: str = "changeme"
    jwt_secret: str = Field(
        default="change-this-secret-in-production",
        validation_alias=AliasChoices("JWT_SECRET", "SECRET_KEY"),
    )
    jwt_expire_hours: int = 24

    model_config = SettingsConfigDict(env_file=".env")


settings = Settings()
