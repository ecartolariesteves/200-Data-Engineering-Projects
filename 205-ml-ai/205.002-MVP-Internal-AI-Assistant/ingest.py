"""
ingest.py
Pipeline de ingesta de documentos.
Soporta: PDF, Word (.docx), Excel (.xlsx)
Estrategia de reemplazo: por nombre de archivo (elimina chunks anteriores)
"""

import os
import hashlib
from pathlib import Path
from typing import List, Dict, Any

import chromadb
from langchain.text_splitter import RecursiveCharacterTextSplitter

from app.config import get_settings
from app.embedding_provider import get_embedding_provider

settings = get_settings()


# ------------------------------------------------------------------ #
# Extractores de texto por tipo de archivo
# ------------------------------------------------------------------ #

def extract_text_from_pdf(file_path: str) -> str:
    """Extrae texto de PDF digital con pymupdf."""
    import fitz  # pymupdf
    doc = fitz.open(file_path)
    text = ""
    for page in doc:
        text += page.get_text()
    doc.close()
    return text


def extract_text_from_docx(file_path: str) -> str:
    """Extrae texto de Word preservando estructura básica."""
    from docx import Document
    doc = Document(file_path)
    paragraphs = []
    for para in doc.paragraphs:
        if para.text.strip():
            paragraphs.append(para.text.strip())
    return "\n".join(paragraphs)


def extract_text_from_excel(file_path: str) -> str:
    """
    Extrae texto de Excel.
    Cada hoja se convierte en texto tabular legible.
    Solo extrae valores (no fórmulas).
    """
    import pandas as pd
    xl = pd.ExcelFile(file_path)
    all_text = []

    for sheet_name in xl.sheet_names:
        df = pd.read_excel(file_path, sheet_name=sheet_name)
        # Eliminar filas completamente vacías
        df = df.dropna(how="all")
        if df.empty:
            continue
        sheet_text = f"[Hoja: {sheet_name}]\n"
        sheet_text += df.to_string(index=False)
        all_text.append(sheet_text)

    return "\n\n".join(all_text)


def extract_text(file_path: str) -> str:
    """Router: detecta tipo de archivo y extrae texto."""
    ext = Path(file_path).suffix.lower()

    extractors = {
        ".pdf":  extract_text_from_pdf,
        ".docx": extract_text_from_docx,
        ".doc":  extract_text_from_docx,
        ".xlsx": extract_text_from_excel,
        ".xls":  extract_text_from_excel,
    }

    if ext not in extractors:
        raise ValueError(f"Formato no soportado: {ext}")

    return extractors[ext](file_path)


# ------------------------------------------------------------------ #
# Chunking
# ------------------------------------------------------------------ #

def split_text(text: str, filename: str) -> List[Dict[str, Any]]:
    """
    Divide el texto en chunks con metadata.
    Usa RecursiveCharacterTextSplitter que respeta párrafos y frases.
    """
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=settings.CHUNK_SIZE,
        chunk_overlap=settings.CHUNK_OVERLAP,
        separators=["\n\n", "\n", ". ", " ", ""],
        length_function=len
    )

    chunks = splitter.split_text(text)

    # Metadata por chunk
    result = []
    for i, chunk in enumerate(chunks):
        chunk_id = hashlib.md5(f"{filename}_{i}_{chunk[:50]}".encode()).hexdigest()
        result.append({
            "id": chunk_id,
            "text": chunk,
            "metadata": {
                "filename": filename,
                "chunk_index": i,
                "total_chunks": len(chunks),
                "source": filename
            }
        })

    return result


# ------------------------------------------------------------------ #
# ChromaDB
# ------------------------------------------------------------------ #

def get_collection():
    """Devuelve la colección ChromaDB. La crea si no existe."""
    client = chromadb.PersistentClient(path=settings.CHROMA_PATH)
    collection = client.get_or_create_collection(
        name=settings.CHROMA_COLLECTION,
        metadata={"hnsw:space": "cosine"}   # distancia coseno para e5
    )
    return collection


def delete_document_chunks(collection, filename: str) -> int:
    """
    Elimina todos los chunks de un documento por nombre de archivo.
    Se llama antes de re-indexar un documento actualizado.
    Devuelve el número de chunks eliminados.
    """
    results = collection.get(
        where={"filename": filename}
    )
    if results["ids"]:
        collection.delete(ids=results["ids"])
        return len(results["ids"])
    return 0


def index_chunks(collection, chunks: List[Dict[str, Any]], embedding_provider) -> int:
    """Indexa los chunks en ChromaDB con sus embeddings."""
    if not chunks:
        return 0

    texts    = [c["text"]     for c in chunks]
    ids      = [c["id"]       for c in chunks]
    metadata = [c["metadata"] for c in chunks]

    embeddings = embedding_provider.embed(texts)

    collection.add(
        ids=ids,
        embeddings=embeddings,
        documents=texts,
        metadatas=metadata
    )

    return len(chunks)


# ------------------------------------------------------------------ #
# Función principal de ingesta
# ------------------------------------------------------------------ #

def ingest_document(file_path: str) -> Dict[str, Any]:
    """
    Ingesta completa de un documento.
    1. Extrae texto
    2. Divide en chunks
    3. Elimina versión anterior (si existe)
    4. Indexa chunks nuevos

    Devuelve resumen de la operación.
    """
    filename = Path(file_path).name

    print(f"[Ingest] Procesando: {filename}")

    # 1. Extraer texto
    text = extract_text(file_path)
    if not text.strip():
        return {"status": "error", "filename": filename, "message": "El documento está vacío o no se pudo extraer texto."}

    # 2. Dividir en chunks
    chunks = split_text(text, filename)
    print(f"[Ingest] {len(chunks)} chunks generados")

    # 3. Reemplazar versión anterior si existe
    collection = get_collection()
    deleted = delete_document_chunks(collection, filename)
    if deleted > 0:
        print(f"[Ingest] Versión anterior eliminada: {deleted} chunks")

    # 4. Generar embeddings e indexar
    embedding_provider = get_embedding_provider()
    indexed = index_chunks(collection, chunks, embedding_provider)

    print(f"[Ingest] {indexed} chunks indexados correctamente")

    return {
        "status": "success",
        "filename": filename,
        "chunks_indexed": indexed,
        "chunks_replaced": deleted,
        "is_update": deleted > 0
    }


def list_indexed_documents() -> List[Dict[str, Any]]:
    """
    Lista todos los documentos indexados con estadísticas.
    Agrupa por nombre de archivo.
    """
    collection = get_collection()
    results = collection.get()

    if not results["ids"]:
        return []

    # Agrupar por documento
    docs: Dict[str, int] = {}
    for meta in results["metadatas"]:
        fname = meta.get("filename", "desconocido")
        docs[fname] = docs.get(fname, 0) + 1

    return [
        {"filename": fname, "chunks": count}
        for fname, count in sorted(docs.items())
    ]


def delete_document(filename: str) -> Dict[str, Any]:
    """Elimina un documento completo del índice."""
    collection = get_collection()
    deleted = delete_document_chunks(collection, filename)

    if deleted == 0:
        return {"status": "not_found", "filename": filename}

    return {"status": "success", "filename": filename, "chunks_deleted": deleted}
