# Asistente Corporativo IA — MVP RAG

Asistente interno basado en documentación corporativa. Responde preguntas de empleados usando únicamente los documentos indexados.

## Stack

| Capa | Tecnología |
|---|---|
| LLM local | Ollama + Llama 3.1 70B |
| Embeddings | multilingual-e5-large |
| Vector DB | ChromaDB |
| Backend | FastAPI + Python |
| Frontend | Streamlit |

## Requisitos

- Python 3.11+
- [Ollama](https://ollama.ai) instalado y corriendo
- GPU recomendada (RTX 3090 o similar para 70B)

## Instalación

```bash
# 1. Clonar y entrar al proyecto
git clone <repo>
cd internal-ai-assistant

# 2. Entorno virtual
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate

# 3. Instalar dependencias
pip install -r requirements.txt

# 4. Configurar entorno
cp .env.example .env
# Editar .env si es necesario

# 5. Descargar modelo LLM
ollama pull llama3.1:70b
```

## Arrancar el sistema

```bash
# Terminal 1 — Backend API
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

# Terminal 2 — Frontend
streamlit run frontend/streamlit_app.py
```

- API: http://localhost:8000
- Docs API: http://localhost:8000/docs
- Frontend: http://localhost:8501

## Cambiar a OpenAI (fase 2)

Editar `.env`:

```
LLM_PROVIDER=openai
LLM_MODEL=gpt-4o
EMBEDDING_PROVIDER=openai
OPENAI_API_KEY=sk-...
```

Sin tocar ningún archivo de código.

## Estructura

```
app/
  config.py              Variables de entorno y settings
  embedding_provider.py  Abstracción embeddings (local ↔ OpenAI)
  llm_provider.py        Abstracción LLM (Ollama ↔ OpenAI)
  ingest.py              Pipeline ingesta de documentos
  rag.py                 Retrieval + construcción de contexto
  main.py                API FastAPI

frontend/
  streamlit_app.py       Chat UI + panel de admin

docs/raw_files/          Documentos originales
vector_db/               ChromaDB persistido
```
