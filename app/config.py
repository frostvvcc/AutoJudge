from pydantic_settings import BaseSettings
from pydantic import Field


class Settings(BaseSettings):
    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}

    llm_backend: str = Field(default="anthropic_proxy", alias="LLM_BACKEND")

    anthropic_api_key: str = Field(default="", alias="ANTHROPIC_API_KEY")

    openai_api_key: str = Field(default="", alias="OPENAI_API_KEY")

    # Anthropic-compatible proxy settings (when llm_backend = "anthropic_proxy")
    anthropic_proxy_base_url: str = Field(default="", alias="ANTHROPIC_PROXY_BASE_URL")
    anthropic_proxy_api_key: str = Field(default="", alias="ANTHROPIC_PROXY_API_KEY")

    # Model names (used when llm_backend = "anthropic_api")
    default_model: str = Field(default="claude-opus-4-6", alias="DEFAULT_MODEL")
    haiku_model: str = Field(default="claude-haiku-4-5-20251001", alias="HAIKU_MODEL")

    # Embedding — uses OpenAI text-embedding-3-small (requires OPENAI_API_KEY).
    # LLM calls use Anthropic Claude; embedding uses OpenAI; ChromaDB is configured
    # with a custom OpenAI embedding function rather than its built-in default model.
    embedding_model: str = "text-embedding-3-small"

    max_rounds: int = 7
    max_tokens_per_debate: int = 100_000
    budget_reserve: float = 0.15

    redis_url: str = "redis://localhost:6379/2"
    chromadb_path: str = "./data/chromadb"

    # MySQL
    mysql_host: str = Field(default="localhost", alias="MYSQL_HOST")
    mysql_port: int = Field(default=3306, alias="MYSQL_PORT")
    mysql_user: str = Field(default="root", alias="MYSQL_USER")
    mysql_password: str = Field(default="", alias="MYSQL_PASSWORD")
    mysql_database: str = Field(default="autojudge", alias="MYSQL_DATABASE")

    @property
    def database_url(self) -> str:
        return (
            f"mysql+aiomysql://{self.mysql_user}:{self.mysql_password}"
            f"@{self.mysql_host}:{self.mysql_port}/{self.mysql_database}"
            f"?charset=utf8mb4"
        )

    # JWT
    jwt_secret: str = Field(
        default="autojudge-dev-secret-change-in-production",
        alias="JWT_SECRET",
    )
    jwt_algorithm: str = "HS256"
    jwt_access_token_expire_minutes: int = Field(
        default=60 * 24, alias="JWT_ACCESS_EXPIRE_MINUTES"
    )
    jwt_refresh_token_expire_days: int = Field(
        default=30, alias="JWT_REFRESH_EXPIRE_DAYS"
    )

    max_concurrent_debates: int = 5
    max_concurrent_llm_calls: int = 20

    langchain_tracing_v2: bool = False
    langchain_api_key: str = ""
    langchain_project: str = "autojudge"

    debug: bool = False


settings = Settings()
