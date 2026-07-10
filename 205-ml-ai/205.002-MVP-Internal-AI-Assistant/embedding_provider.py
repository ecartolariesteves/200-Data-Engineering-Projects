"""
embedding_provider.py
Capa de abstracción para embeddings.
Cambiar de local a OpenAI: editar EMBEDDING_PROVIDER en .env
Sin tocar nada más en el sistema.
"""

from abc import ABC, abstractmethod
from typing import List
from app.config import get_settings

settings = get_settings()


# ------------------------------------------------------------------ #
# Interfaz base
# ------------------------------------------------------------------ #

class BaseEmbeddingProvider(ABC):
    """
    Contrato que deben cumplir todos los proveedores de embeddings.
    Cualquier proveedor nuevo solo necesita implementar embed().
    """

    @abstractmethod
    def embed(self, texts: List[str]) -> List[List[float]]:
        """
        Recibe una lista de textos.
        Devuelve una lista de vectores (uno por texto).
        """
        ...

    def embed_single(self, text: str) -> List[float]:
        """Shortcut para embeber un solo texto (query del usuario)."""
        return self.embed([text])[0]


# ------------------------------------------------------------------ #
# Proveedor local — multilingual-e5-large (sentence-transformers)
# ------------------------------------------------------------------ #

class LocalEmbeddingProvider(BaseEmbeddingProvider):
    """
    Embeddings locales con multilingual-e5-large.
    Ideal para documentos en español. Coste $0. Datos no salen del servidor.

    multilingual-e5-large requiere prefijos en los textos:
    - "query: " para preguntas del usuario
    - "passage: " para fragmentos de documentos
    Esto mejora significativamente la calidad del retrieval.
    """

    def __init__(self):
        # Carga diferida: el modelo se carga solo cuando se necesita
        self._model = None

    def _get_model(self):
        if self._model is None:
            from sentence_transformers import SentenceTransformer
            print(f"[Embeddings] Cargando modelo local: {settings.EMBEDDING_MODEL_LOCAL}")
            self._model = SentenceTransformer(
                settings.EMBEDDING_MODEL_LOCAL,
                device="cuda"   # GPU — RTX 3090 disponible
            )
            print("[Embeddings] Modelo local cargado correctamente.")
        return self._model

    def embed(self, texts: List[str]) -> List[List[float]]:
        model = self._get_model()
        # Añadimos prefijo "passage:" para fragmentos de documentos
        prefixed = [f"passage: {t}" for t in texts]
        vectors = model.encode(prefixed, normalize_embeddings=True)
        return vectors.tolist()

    def embed_query(self, query: str) -> List[float]:
        """
        Para queries del usuario se usa prefijo "query:" (distinto a documentos).
        Esto es específico de multilingual-e5-large y mejora el retrieval.
        """
        model = self._get_model()
        vector = model.encode(f"query: {query}", normalize_embeddings=True)
        return vector.tolist()


# ------------------------------------------------------------------ #
# Proveedor OpenAI (fase 2)
# ------------------------------------------------------------------ #

class OpenAIEmbeddingProvider(BaseEmbeddingProvider):
    """
    Embeddings via OpenAI API.
    Activar: EMBEDDING_PROVIDER=openai en .env
    Requiere: OPENAI_API_KEY en .env
    """

    def __init__(self):
        if not settings.OPENAI_API_KEY:
            raise ValueError(
                "OPENAI_API_KEY no configurada. "
                "Añádela al .env o usa EMBEDDING_PROVIDER=local"
            )
        import openai
        self._client = openai.OpenAI(api_key=settings.OPENAI_API_KEY)

    def embed(self, texts: List[str]) -> List[List[float]]:
        response = self._client.embeddings.create(
            model=settings.EMBEDDING_MODEL_OPENAI,
            input=texts
        )
        return [item.embedding for item in response.data]

    def embed_query(self, query: str) -> List[float]:
        # OpenAI no usa prefijos, misma función para query y documentos
        return self.embed_single(query)


# ------------------------------------------------------------------ #
# Factory — punto de entrada único
# ------------------------------------------------------------------ #

def get_embedding_provider() -> BaseEmbeddingProvider:
    """
    Devuelve el proveedor configurado en .env.
    Uso: provider = get_embedding_provider()
    """
    provider = settings.EMBEDDING_PROVIDER.lower()

    if provider == "local":
        return LocalEmbeddingProvider()
    elif provider == "openai":
        return OpenAIEmbeddingProvider()
    else:
        raise ValueError(
            f"EMBEDDING_PROVIDER='{provider}' no reconocido. "
            f"Valores válidos: 'local', 'openai'"
        )
