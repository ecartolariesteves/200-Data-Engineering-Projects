"""
streamlit_app.py
Frontend del asistente corporativo.
Interfaz de chat para empleados + panel de admin para gestión de documentos.
"""

import streamlit as st
import requests
from pathlib import Path

API_URL = "http://localhost:8000"

# ------------------------------------------------------------------ #
# Configuración de página
# ------------------------------------------------------------------ #

st.set_page_config(
    page_title="Asistente Corporativo",
    page_icon="🏢",
    layout="wide"
)

# ------------------------------------------------------------------ #
# Sidebar — navegación y estado del sistema
# ------------------------------------------------------------------ #

with st.sidebar:
    st.title("🏢 Asistente Corporativo")
    st.divider()

    # Selector de sección
    section = st.radio(
        "Sección",
        ["💬 Chat", "📁 Administración"],
        label_visibility="collapsed"
    )

    st.divider()

    # Estado del sistema
    st.caption("Estado del sistema")
    try:
        health = requests.get(f"{API_URL}/health", timeout=3).json()
        st.success("API conectada")
        st.caption(f"Modelo: `{health.get('model', '-')}`")
        st.caption(f"LLM: `{health.get('llm_provider', '-')}`")
        st.caption(f"Embeddings: `{health.get('embedding_provider', '-')}`")
    except Exception:
        st.error("API no disponible")
        st.caption("Inicia el backend con:\n`uvicorn app.main:app --reload`")


# ------------------------------------------------------------------ #
# SECCIÓN: Chat
# ------------------------------------------------------------------ #

if section == "💬 Chat":

    st.header("💬 Pregunta sobre los documentos corporativos")
    st.caption("Haz preguntas sobre políticas, procedimientos y documentación interna.")

    # Inicializar historial de chat
    if "messages" not in st.session_state:
        st.session_state.messages = []

    # Mostrar historial
    for msg in st.session_state.messages:
        with st.chat_message(msg["role"]):
            st.markdown(msg["content"])
            if msg.get("sources"):
                with st.expander("📄 Fuentes consultadas"):
                    for src in msg["sources"]:
                        st.caption(f"• {src}")

    # Input de pregunta
    if question := st.chat_input("¿En qué puedo ayudarte?"):

        # Mostrar pregunta del usuario
        st.session_state.messages.append({"role": "user", "content": question})
        with st.chat_message("user"):
            st.markdown(question)

        # Obtener respuesta con streaming
        with st.chat_message("assistant"):
            response_placeholder = st.empty()
            sources_placeholder  = st.empty()

            full_response = ""

            try:
                with requests.post(
                    f"{API_URL}/chat/stream",
                    json={"question": question},
                    stream=True,
                    timeout=120
                ) as resp:
                    if resp.status_code == 200:
                        for chunk in resp.iter_content(chunk_size=None, decode_unicode=True):
                            if chunk:
                                full_response += chunk
                                response_placeholder.markdown(full_response + "▌")

                        response_placeholder.markdown(full_response)

                    else:
                        error = resp.json().get("detail", "Error desconocido")
                        full_response = f"❌ Error: {error}"
                        response_placeholder.error(full_response)

            except requests.exceptions.ConnectionError:
                full_response = "❌ No se puede conectar con la API. ¿Está el backend corriendo?"
                response_placeholder.error(full_response)

            # Obtener fuentes usadas (llamada separada no bloqueante)
            sources = []
            try:
                sources_resp = requests.post(
                    f"{API_URL}/chat",
                    json={"question": question},
                    timeout=120
                ).json()
                sources = sources_resp.get("sources", [])
                if sources:
                    with sources_placeholder.expander("📄 Fuentes consultadas"):
                        for src in sources:
                            st.caption(f"• {src}")
            except Exception:
                pass

        # Guardar respuesta en historial
        st.session_state.messages.append({
            "role": "assistant",
            "content": full_response,
            "sources": sources
        })

    # Botón para limpiar historial
    if st.session_state.messages:
        if st.button("🗑️ Limpiar conversación", use_container_width=False):
            st.session_state.messages = []
            st.rerun()


# ------------------------------------------------------------------ #
# SECCIÓN: Administración
# ------------------------------------------------------------------ #

elif section == "📁 Administración":

    st.header("📁 Gestión de documentos")
    st.caption("Panel de administración para gestionar la base de conocimiento.")

    col1, col2 = st.columns([1, 1], gap="large")

    # ---- Columna izquierda: subir documentos ----
    with col1:
        st.subheader("Subir documento")

        uploaded_file = st.file_uploader(
            "Selecciona un archivo",
            type=["pdf", "docx", "doc", "xlsx", "xls"],
            help="Formatos soportados: PDF, Word, Excel"
        )

        if uploaded_file:
            st.info(f"📄 **{uploaded_file.name}** ({uploaded_file.size / 1024:.1f} KB)")

            if st.button("📤 Indexar documento", type="primary", use_container_width=True):
                with st.spinner("Procesando documento..."):
                    try:
                        response = requests.post(
                            f"{API_URL}/admin/documents/upload",
                            files={"file": (uploaded_file.name, uploaded_file.getvalue())}
                        )

                        if response.status_code == 200:
                            result = response.json()
                            if result.get("is_update"):
                                st.success(
                                    f"✅ Documento actualizado: **{result['filename']}**\n\n"
                                    f"Chunks reemplazados: {result['chunks_replaced']} → {result['chunks_indexed']}"
                                )
                            else:
                                st.success(
                                    f"✅ Documento indexado: **{result['filename']}**\n\n"
                                    f"Chunks creados: {result['chunks_indexed']}"
                                )
                        else:
                            st.error(f"❌ Error: {response.json().get('detail', 'Error desconocido')}")

                    except requests.exceptions.ConnectionError:
                        st.error("❌ No se puede conectar con la API.")

    # ---- Columna derecha: documentos indexados ----
    with col2:
        st.subheader("Documentos indexados")

        try:
            docs_response = requests.get(f"{API_URL}/admin/documents", timeout=5).json()
            docs = docs_response.get("documents", [])

            if not docs:
                st.info("No hay documentos indexados todavía.")
            else:
                st.caption(f"{len(docs)} documento(s) en la base de conocimiento")

                for doc in docs:
                    col_name, col_chunks, col_del = st.columns([3, 1, 1])

                    with col_name:
                        st.text(doc["filename"])
                    with col_chunks:
                        st.caption(f"{doc['chunks']} chunks")
                    with col_del:
                        if st.button("🗑️", key=f"del_{doc['filename']}", help=f"Eliminar {doc['filename']}"):
                            try:
                                del_resp = requests.delete(
                                    f"{API_URL}/admin/documents/{doc['filename']}",
                                    timeout=5
                                )
                                if del_resp.status_code == 200:
                                    st.success(f"Eliminado: {doc['filename']}")
                                    st.rerun()
                                else:
                                    st.error("Error al eliminar")
                            except Exception:
                                st.error("Error de conexión")

        except requests.exceptions.ConnectionError:
            st.error("❌ No se puede conectar con la API.")
