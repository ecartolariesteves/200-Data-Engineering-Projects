"""
main.py
API FastAPI del asistente corporativo.
Endpoints para chat y gestión de documentos (admin).
"""

import os
import shutil
from pathlib import Path
from typing import List

from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from app.config import get_settings
from app.ingest import ingest_document, list_indexed_documents, delete_document
from app.rag import ask, ask_stream

settings = get_settings()

app = FastAPI(
    title="Asistente Corporativo IA",
    description="Asistente interno basado en documentación corporativa",
    version="1.0.0"
)


# ------------------------------------------------------------------ #
# Modelos de request/response
# ------------------------------------------------------------------ #

class QuestionRequest(BaseModel):
    question: str


class AnswerResponse(BaseModel):
    answer: str
    sources: List[str]
    chunks_used: int


# ------------------------------------------------------------------ #
# Health check
# ------------------------------------------------------------------ #

@app.get("/health")
def health_check():
    return {
        "status": "ok",
        "llm_provider": settings.LLM_PROVIDER,
        "embedding_provider": settings.EMBEDDING_PROVIDER,
        "model": settings.LLM_MODEL
    }


# ------------------------------------------------------------------ #
# Chat endpoints
# ------------------------------------------------------------------ #

@app.post("/chat", response_model=AnswerResponse)
def chat(request: QuestionRequest):
    """
    Pregunta al asistente (respuesta completa).
    Usa el pipeline RAG completo.
    """
    if not request.question.strip():
        raise HTTPException(status_code=400, detail="La pregunta no puede estar vacía.")

    result = ask(request.question)
    return AnswerResponse(**result)


@app.post("/chat/stream")
def chat_stream(request: QuestionRequest):
    """
    Pregunta al asistente con respuesta en streaming.
    Ideal para el frontend Streamlit — respuesta token a token.
    """
    if not request.question.strip():
        raise HTTPException(status_code=400, detail="La pregunta no puede estar vacía.")

    def generate():
        yield from ask_stream(request.question)

    return StreamingResponse(generate(), media_type="text/plain")


# ------------------------------------------------------------------ #
# Admin endpoints — gestión de documentos
# ------------------------------------------------------------------ #

@app.post("/admin/documents/upload")
async def upload_document(file: UploadFile = File(...)):
    """
    Sube e indexa un documento.
    Si ya existe un documento con el mismo nombre, lo reemplaza.
    Formatos soportados: PDF, DOCX, XLSX
    """
    ALLOWED_EXTENSIONS = {".pdf", ".docx", ".doc", ".xlsx", ".xls"}
    ext = Path(file.filename).suffix.lower()

    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=f"Formato no soportado: {ext}. Permitidos: {', '.join(ALLOWED_EXTENSIONS)}"
        )

    # Guardar archivo temporalmente
    docs_path = Path(settings.DOCS_PATH)
    docs_path.mkdir(parents=True, exist_ok=True)
    file_path = docs_path / file.filename

    with open(file_path, "wb") as f:
        shutil.copyfileobj(file.file, f)

    # Ingestar
    result = ingest_document(str(file_path))

    if result["status"] == "error":
        raise HTTPException(status_code=422, detail=result["message"])

    return result


@app.get("/admin/documents")
def list_documents():
    """Lista todos los documentos indexados."""
    docs = list_indexed_documents()
    return {"documents": docs, "total": len(docs)}


@app.delete("/admin/documents/{filename}")
def remove_document(filename: str):
    """Elimina un documento del índice."""
    result = delete_document(filename)

    if result["status"] == "not_found":
        raise HTTPException(
            status_code=404,
            detail=f"Documento '{filename}' no encontrado en el índice."
        )

    return result


# ------------------------------------------------------------------ #
# Entry point
# ------------------------------------------------------------------ #

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "app.main:app",
        host=settings.API_HOST,
        port=settings.API_PORT,
        reload=True
    )
