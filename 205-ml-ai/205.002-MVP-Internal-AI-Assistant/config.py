"""
config.py
Configuración central del sistema.
Todas las variables se leen desde .env o tienen valores por defecto.
Para cambiar de local a OpenAI: editar LLM_PROVIDER y EMBEDDING_PROVIDER en .env
"""

from pydantic_settings import BaseSettings
from functools import lru_cache


class Settings(BaseSettings):
    # ------------------------------------------------------------------ #
    # LLM
    # ------------------------------------------------------------------ #
    LLM_PROVIDER: str = "local"          # "local" | "openai" | "azure"
    LLM_MODEL: str = "llama3.1:70b"      # modelo Ollama o nombre OpenAI
    LLM_TEMPERATURE: float = 0.0         # 0 = determinista, ideal para RAG

    # ------------------------------------------------------------------ #
    # Embeddings
    # ------------------------------------------------------------------ #
    EMBEDDING_PROVIDER: str = "local"    # "local" | "openai"
    # Modelo local (sentence-transformers)
    EMBEDDING_MODEL_LOCAL: str = "intfloat/multilingual-e5-large"
    # Modelo OpenAI (futuro)
    EMBEDDING_MODEL_OPENAI: str = "text-embedding-3-large"
    EMBEDDING_DIMENSION: int = 1024      # dimensión de multilingual-e5-large

    # ------------------------------------------------------------------ #
    # Ollama
    # ------------------------------------------------------------------ #
    OLLAMA_BASE_URL: str = "http://localhost:11434"

    # ------------------------------------------------------------------ #
    # OpenAI (fase 2)
    # ------------------------------------------------------------------ #
    OPENAI_API_KEY: str = ""

    # ------------------------------------------------------------------ #
    # ChromaDB
    # ------------------------------------------------------------------ #
    CHROMA_PATH: str = "./vector_db"
    CHROMA_COLLECTION: str = "corporate_docs"

    # ------------------------------------------------------------------ #
    # Documentos
    # ------------------------------------------------------------------ #
    DOCS_PATH: str = "./docs/raw_files"

    # ------------------------------------------------------------------ #
    # Chunking
    # ------------------------------------------------------------------ #
    CHUNK_SIZE: int = 800
    CHUNK_OVERLAP: int = 100

    # ------------------------------------------------------------------ #
    # Retrieval
    # ------------------------------------------------------------------ #
    RETRIEVAL_TOP_K: int = 4             # chunks más relevantes a recuperar

    # ------------------------------------------------------------------ #
    # API
    # ------------------------------------------------------------------ #
    API_HOST: str = "0.0.0.0"
    API_PORT: int = 8000

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        extra = "ignore"


@lru_cache()
def get_settings() -> Settings:
    """
    Singleton: la configuración se carga una sola vez.
    Usar siempre get_settings() en lugar de instanciar Settings() directamente.
    """
    return Settings()
