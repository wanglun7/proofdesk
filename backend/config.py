from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    postgres_dsn: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/proofdesk"
    openai_api_key: str = ""
    openai_base_url: str = "https://api.openai.com/v1"
    openai_model: str = "gpt-4o"
    dashscope_api_key: str = ""
    embedding_model: str = "text-embedding-v3"
    reranker_model: str = "gte-rerank"
    embed_dim: int = 1024

    class Config:
        env_file = ".env"


settings = Settings()
