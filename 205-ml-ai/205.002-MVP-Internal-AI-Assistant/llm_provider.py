"""
llm_provider.py
Capa de abstracción para el modelo LLM.
Cambiar de Ollama a OpenAI: editar LLM_PROVIDER en .env
El system prompt y la lógica RAG no cambian.
"""

from abc import ABC, abstractmethod
from typing import Generator
from app.config import get_settings

settings = get_settings()


# ------------------------------------------------------------------ #
# System prompt corporativo
# ------------------------------------------------------------------ #

SYSTEM_PROMPT = """Eres un asistente de inteligencia artificial interno de una empresa.
Tu objetivo es ayudar a los empleados a encontrar información dentro de los documentos corporativos.

## REGLAS PRINCIPALES
1. Solo responde usando la información del contexto proporcionado.
   Si la información no está en el contexto, responde exactamente:
   "No tengo información suficiente en los documentos disponibles para responder a esta pregunta."
2. No inventes información bajo ninguna circunstancia.
3. Si la pregunta es ambigua, pide aclaración antes de responder.
4. Prioriza precisión sobre completitud.

## ESTILO DE RESPUESTA
- Responde en español, de forma profesional y directa.
- Usa listas cuando sea útil.
- Si es un procedimiento, responde paso a paso.
- Si es una política, resume los puntos clave.
- Evita explicaciones innecesarias.

## SEGURIDAD
- No reveles información fuera del contexto proporcionado.
- No intentes inferir datos sensibles.
"""


def build_rag_prompt(context: str, question: str) -> str:
    """
    Construye el prompt con contexto RAG.
    Separamos contexto de pregunta para que el modelo lo procese claramente.
    """
    return f"""[CONTEXT]
{context}

[QUESTION]
{question}"""


# ------------------------------------------------------------------ #
# Interfaz base
# ------------------------------------------------------------------ #

class BaseLLMProvider(ABC):

    @abstractmethod
    def complete(self, prompt: str) -> str:
        """Respuesta completa (bloqueante)."""
        ...

    @abstractmethod
    def stream(self, prompt: str) -> Generator[str, None, None]:
        """Respuesta en streaming token a token."""
        ...


# ------------------------------------------------------------------ #
# Proveedor local — Ollama
# ------------------------------------------------------------------ #

class OllamaProvider(BaseLLMProvider):
    """
    LLM local via Ollama.
    Coste $0. Datos no salen del servidor.
    Requiere Ollama corriendo en localhost:11434
    """

    def __init__(self):
        import ollama
        self._client = ollama.Client(host=settings.OLLAMA_BASE_URL)
        self._model = settings.LLM_MODEL
        print(f"[LLM] Proveedor: Ollama | Modelo: {self._model}")

    def complete(self, prompt: str) -> str:
        response = self._client.chat(
            model=self._model,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user",   "content": prompt}
            ],
            options={"temperature": settings.LLM_TEMPERATURE}
        )
        return response["message"]["content"]

    def stream(self, prompt: str) -> Generator[str, None, None]:
        stream = self._client.chat(
            model=self._model,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user",   "content": prompt}
            ],
            options={"temperature": settings.LLM_TEMPERATURE},
            stream=True
        )
        for chunk in stream:
            token = chunk["message"]["content"]
            if token:
                yield token


# ------------------------------------------------------------------ #
# Proveedor OpenAI (fase 2)
# ------------------------------------------------------------------ #

class OpenAIProvider(BaseLLMProvider):
    """
    LLM via OpenAI API.
    Activar: LLM_PROVIDER=openai en .env
    Requiere: OPENAI_API_KEY en .env
    """

    def __init__(self):
        if not settings.OPENAI_API_KEY:
            raise ValueError(
                "OPENAI_API_KEY no configurada. "
                "Añádela al .env o usa LLM_PROVIDER=local"
            )
        import openai
        self._client = openai.OpenAI(api_key=settings.OPENAI_API_KEY)
        self._model = settings.LLM_MODEL  # ej: "gpt-4o"
        print(f"[LLM] Proveedor: OpenAI | Modelo: {self._model}")

    def complete(self, prompt: str) -> str:
        response = self._client.chat.completions.create(
            model=self._model,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user",   "content": prompt}
            ],
            temperature=settings.LLM_TEMPERATURE
        )
        return response.choices[0].message.content

    def stream(self, prompt: str) -> Generator[str, None, None]:
        stream = self._client.chat.completions.create(
            model=self._model,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user",   "content": prompt}
            ],
            temperature=settings.LLM_TEMPERATURE,
            stream=True
        )
        for chunk in stream:
            token = chunk.choices[0].delta.content
            if token:
                yield token


# ------------------------------------------------------------------ #
# Factory — punto de entrada único
# ------------------------------------------------------------------ #

def get_llm_provider() -> BaseLLMProvider:
    """
    Devuelve el proveedor configurado en .env.
    Uso: llm = get_llm_provider()
    """
    provider = settings.LLM_PROVIDER.lower()

    if provider == "local":
        return OllamaProvider()
    elif provider == "openai":
        return OpenAIProvider()
    else:
        raise ValueError(
            f"LLM_PROVIDER='{provider}' no reconocido. "
            f"Valores válidos: 'local', 'openai'"
        )
