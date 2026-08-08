"""
Centralized configuration for the AI service.
Validate environment variables and provide default values.

"""
from functools import lru_cache
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    """
    Configuration settings for the AI service.
    """

    # Required secrets should come from environment variables.
    GROQ_API_KEY: str
    LANGCHAIN_API_KEY: str
    NVIDIA_API_KEY: str
    LOGFIRE_API_KEY: str
    NEMOGUARDRAILS_LLM_FRAMEWORK: str = "langchain" 
    QDRANT_API_KEY: str
    HF_TOKEN: str

    # LLM
    primary_model: str = "default_primary_model"
    secondary_model: str = "default_secondary_model"

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


@lru_cache
def get_settings() -> Settings:
    """Return cached settings so env parsing happens once per process."""
    return Settings()  # pyright: ignore[reportCallIssue]
