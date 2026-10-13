"""
rag.py
Pipeline RAG: retrieval + construcción de contexto + respuesta.
Este es el núcleo del sistema.
"""

from typing import List, Dict, Any, Generator

from app.config import get_settings
from app.embedding_provider import get_embedding_provider, LocalEmbeddingProvider
from app.llm_provider import get_llm_provider, build_rag_prompt
from app.ingest import get_collection

settings = get_settings()


# ------------------------------------------------------------------ #
# Retrieval
# ------------------------------------------------------------------ #

def retrieve_chunks(query: str, top_k: int = None) -> List[Dict[str, Any]]:
    """
    Busca los chunks más relevantes para una query.
    Devuelve lista de chunks con texto, metadata y score de relevancia.
    """
    top_k = top_k or settings.RETRIEVAL_TOP_K
    collection = get_collection()

    # Total de documentos indexados
    total = collection.count()
    if total == 0:
        return []

    # Limitar top_k al total disponible
    top_k = min(top_k, total)

    # Embeber la query
    # Nota: LocalEmbeddingProvider tiene embed_query() con prefijo "query:"
    # Los demás proveedores usan embed_single()
    embedding_provider = get_embedding_provider()
    if isinstance(embedding_provider, LocalEmbeddingProvider):
        query_embedding = embedding_provider.embed_query(query)
    else:
        query_embedding = embedding_provider.embed_single(query)

    # Búsqueda semántica
    results = collection.query(
        query_embeddings=[query_embedding],
        n_results=top_k,
        include=["documents", "metadatas", "distances"]
    )

    # Formatear resultados
    chunks = []
    for i in range(len(results["ids"][0])):
        distance = results["distances"][0][i]
        # Convertir distancia coseno a score de similitud (0-1)
        similarity = 1 - distance

        chunks.append({
            "text":       results["documents"][0][i],
            "metadata":   results["metadatas"][0][i],
            "similarity": round(similarity, 4),
            "source":     results["metadatas"][0][i].get("filename", "desconocido")
        })

    # Ordenar por relevancia descendente
    chunks.sort(key=lambda x: x["similarity"], reverse=True)

    return chunks


def build_context(chunks: List[Dict[str, Any]]) -> str:
    """
    Construye el bloque de contexto a partir de los chunks recuperados.
    Incluye referencia al documento fuente para trazabilidad.
    """
    if not chunks:
        return ""

    context_parts = []
    for chunk in chunks:
        source = chunk["metadata"].get("filename", "desconocido")
        context_parts.append(
            f"[Fuente: {source}]\n{chunk['text']}"
        )

    return "\n\n---\n\n".join(context_parts)


# ------------------------------------------------------------------ #
# Pipeline RAG completo
# ------------------------------------------------------------------ #

def ask(query: str) -> Dict[str, Any]:
    """
    Pipeline RAG completo (respuesta bloqueante).

    Flujo:
    1. Retrieval: busca chunks relevantes
    2. Contexto: construye bloque de texto
    3. Prompt: combina contexto + pregunta
    4. LLM: genera respuesta
    5. Devuelve respuesta + fuentes
    """

    # 1. Retrieval
    chunks = retrieve_chunks(query)

    if not chunks:
        return {
            "answer": "No tengo información suficiente en los documentos disponibles para responder a esta pregunta.",
            "sources": [],
            "chunks_used": 0
        }

    # Filtro de relevancia mínima
    # Chunks con similitud muy baja probablemente no son útiles
    MIN_SIMILARITY = 0.3
    relevant_chunks = [c for c in chunks if c["similarity"] >= MIN_SIMILARITY]

    if not relevant_chunks:
        return {
            "answer": "No tengo información suficiente en los documentos disponibles para responder a esta pregunta.",
            "sources": [],
            "chunks_used": 0
        }

    # 2. Construir contexto
    context = build_context(relevant_chunks)

    # 3. Construir prompt RAG
    prompt = build_rag_prompt(context=context, question=query)

    # 4. Llamar al LLM
    llm = get_llm_provider()
    answer = llm.complete(prompt)

    # 5. Fuentes únicas usadas
    sources = list({c["source"] for c in relevant_chunks})

    return {
        "answer": answer,
        "sources": sources,
        "chunks_used": len(relevant_chunks)
    }


def ask_stream(query: str) -> Generator[str, None, None]:
    """
    Pipeline RAG con respuesta en streaming.
    Yield token a token para UI reactiva.
    """

    # Retrieval (mismo que ask())
    chunks = retrieve_chunks(query)

    if not chunks:
        yield "No tengo información suficiente en los documentos disponibles para responder a esta pregunta."
        return

    MIN_SIMILARITY = 0.3
    relevant_chunks = [c for c in chunks if c["similarity"] >= MIN_SIMILARITY]

    if not relevant_chunks:
        yield "No tengo información suficiente en los documentos disponibles para responder a esta pregunta."
        return

    context = build_context(relevant_chunks)
    prompt = build_rag_prompt(context=context, question=query)

    llm = get_llm_provider()
    yield from llm.stream(prompt)


def get_sources_for_query(query: str) -> List[Dict[str, Any]]:
    """
    Devuelve solo las fuentes relevantes sin llamar al LLM.
    Útil para mostrar al usuario qué documentos se consultaron.
    """
    chunks = retrieve_chunks(query)
    return [
        {
            "source": c["source"],
            "similarity": c["similarity"],
            "preview": c["text"][:150] + "..."
        }
        for c in chunks
    ]
