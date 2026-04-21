from pydantic_settings import BaseSettings
from pydantic import ConfigDict


class Settings(BaseSettings):
    model_config = ConfigDict(env_file=".env")

    DATABASE_URL: str = "postgresql://clusterizer:clusterizer@localhost:5432/clusterizer"

    # Ollama configuration
    OLLAMA_URL: str = "http://localhost:11434"
    # Embedding model (any Ollama model that supports /api/embed).
    # Small Gemma-based options: "gemma3:2b"  General-purpose: "nomic-embed-text"
    OLLAMA_EMBED_MODEL: str = "nomic-embed-text"
    # Vector dimension MUST match the embedding model output.
    # nomic-embed-text → 768  |  mxbai-embed-large → 1024  |  gemma3:2b → 2048
    OLLAMA_EMBED_DIM: int = 768
    # LLM used to generate human-readable cluster labels.
    # "gemma3:4b" is fast and cheap locally (≈4 GB RAM).
    OLLAMA_LLM_MODEL: str = "gemma3:4b"


settings = Settings()
