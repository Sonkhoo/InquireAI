"""
Centralized configuration for the AI service.
Validate environment variables and provide default values.

"""
from functools import lru_cache
from pydantic_settings import BaseSettings
from urllib.parse import quote_plus

class Settings(BaseSettings):
    """
    Configuration settings for the AI service.
    """
    # Database configuration
    POSTGRES_USER: str
    POSTGRES_PASSWORD: str
    POSTGRES_DB: str
    POSTGRES_HOST: str  
    POSTGRES_PORT: int 
    DB_POOL_SIZE: int = 5
    STM_MAX_MESSAGES: int = 10 
    # Required secrets should come from environment variables.
    GROQ_API_KEY: str
    LANGCHAIN_API_KEY: str
    LOGFIRE_API_KEY: str
    QDRANT_API_KEY: str
    JINA_API_KEY: str
    QDRANT_URL: str
    HF_TOKEN: str

    # LLM
    dense_model: str = "jinaai/jina-embeddings-v4"
    sparse_model: str = "Qdrant/bm25"
    enrich_model: str = "openai/gpt-oss-120b"
    secondary_model: str = "openai/gpt-oss-20b"

    #Langchain settings
    LANGCHAIN_TRACING: bool = True
    LANGCHAIN_PROJECT: str = "InquireAI"

    #Application settings
    APP_ENV: str = "development"
    LOG_LEVEL: str = "debug"   
    LOG_FORMAT: str = "json"
    CACHE_TTL: int = 3600  
    MAX_TRIES: int = 3

    model_config = {
        "env_file": ".env",
        "env_file_encoding": "utf-8",
        "extra": "ignore",
    }

    @property
    def is_production(self) -> bool:
        """Check if the application is running in production."""
        return self.APP_ENV.lower() == "production"

    @property
    def db_url(self) -> str:
        return (
            f"postgresql://{self.POSTGRES_USER}:{quote_plus(self.POSTGRES_PASSWORD)}"
            f"@{self.POSTGRES_HOST}:{self.POSTGRES_PORT}/{self.POSTGRES_DB}"
            "?sslmode=disable&options=-c%20timezone%3DUTC"
        )

    

@lru_cache
def get_settings() -> Settings:
    """Return cached settings so env parsing happens once per process."""
    return Settings()  # pyright: ignore[reportCallIssue]
