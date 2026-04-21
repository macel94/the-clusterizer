from pydantic_settings import BaseSettings
from pydantic import ConfigDict


class Settings(BaseSettings):
    model_config = ConfigDict(env_file=".env")

    DATABASE_URL: str = "postgresql://clusterizer:clusterizer@localhost:5432/clusterizer"

    # Ollama configuration
    OLLAMA_URL: str = "http://localhost:11434"
    # EmbeddingGemma is the default embedding model because it is optimized for
    # retrieval, semantic similarity, and clustering workloads.
    OLLAMA_EMBED_MODEL: str = "embeddinggemma"
    # Vector dimension MUST match the embedding model output.
    # embeddinggemma defaults to 768 dimensions in this app.
    OLLAMA_EMBED_DIM: int = 768
    # LLM used to generate human-readable cluster labels.
    # gemma4:e4b keeps the smaller Gemma 4 edge variant explicit for local use.
    OLLAMA_LLM_MODEL: str = "gemma4:e4b"
    OLLAMA_RETRY_ATTEMPTS: int = 3
    OLLAMA_RETRY_INITIAL_BACKOFF_SECONDS: float = 1.0
    OLLAMA_RETRY_BACKOFF_MULTIPLIER: float = 2.0
    OLLAMA_RETRY_MAX_BACKOFF_SECONDS: float = 8.0
    OLLAMA_EMBED_BATCH_SIZE: int = 64


settings = Settings()
