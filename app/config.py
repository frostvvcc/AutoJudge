from pydantic_settings import BaseSettings
from pydantic import Field


class Settings(BaseSettings):
    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}

    # LLM backend: "claude_cli" (claude -p) or "anthropic_api" (direct SDK)
    llm_backend: str = Field(default="claude_cli", alias="LLM_BACKEND")

    # Only needed when llm_backend = "anthropic_api"
    anthropic_api_key: str = Field(default="", alias="ANTHROPIC_API_KEY")

    # Only needed for ChromaDB embedding (Memory Layer 1 & 3)
    # If empty, ChromaDB uses its default embedding model (no external API needed)
    openai_api_key: str = Field(default="", alias="OPENAI_API_KEY")

    # claude -p settings
    claude_cli_path: str = Field(default="claude", alias="CLAUDE_CLI_PATH")
    claude_cli_model: str = Field(default="", alias="CLAUDE_CLI_MODEL")
    claude_cli_timeout: int = Field(default=120, alias="CLAUDE_CLI_TIMEOUT")

    # Model names (used when llm_backend = "anthropic_api")
    default_model: str = "claude-sonnet-4-20250514"
    haiku_model: str = "claude-haiku-4-5-20251001"

    embedding_model: str = "text-embedding-3-small"

    max_rounds: int = 7
    max_tokens_per_debate: int = 100_000
    budget_reserve: float = 0.15

    redis_url: str = "redis://localhost:6379/2"
    chromadb_path: str = "./data/chromadb"

    max_concurrent_debates: int = 5
    max_concurrent_llm_calls: int = 20

    langchain_tracing_v2: bool = False
    langchain_api_key: str = ""
    langchain_project: str = "autojudge"

    debug: bool = False


settings = Settings()
