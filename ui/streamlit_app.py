"""Streamlit UI for the assignment.

Shows:
- Upload PDF
- Chat
- Generate handbook

Run:
  streamlit run ui/streamlit_app.py
"""

import os
import requests
import streamlit as st

API_BASE = os.getenv("API_BASE", "http://localhost:8000")

st.set_page_config(page_title="Handbook Generator", layout="wide")
st.title("📄→🧠 LightRAG → 💬 Chat → 📖 Handbook (FastAPI + Grok 4.1)")

with st.sidebar:
    st.header("API")
    api = st.text_input("API Base URL", API_BASE)
    st.caption("Set env var API_BASE or edit here.")
    API_BASE = api.rstrip("/")

st.subheader("1) Upload PDF")
uploaded = st.file_uploader("Choose a PDF", type=["pdf"])

if "document_id" not in st.session_state:
    st.session_state["document_id"] = ""

if uploaded is not None and st.button("Upload & Index"):
    files = {"file": (uploaded.name, uploaded.getvalue(), "application/pdf")}
    r = requests.post(f"{API_BASE}/api/upload", files=files, timeout=300)
    if r.ok:
        data = r.json()
        st.session_state["document_id"] = data["document_id"]
        st.success(f"Indexed {data['chunks_indexed']} chunks. document_id={data['document_id']}")
    else:
        st.error(r.text)

doc_id = st.session_state.get("document_id", "")
st.info(f"Current document_id: {doc_id or '(none)'}")

st.divider()

col1, col2 = st.columns(2)

with col1:
    st.subheader("2) Chat")
    question = st.text_input("Ask a question about the uploaded document(s):")
    if st.button("Ask") and doc_id and question:
        payload = {"document_id": doc_id, "question": question, "chat_history": []}
        r = requests.post(f"{API_BASE}/api/chat", json=payload, timeout=300)
        if r.ok:
            data = r.json()
            st.markdown("### Answer")
            st.write(data["answer"])
            if data.get("citations"):
                st.markdown("### Citations")
                for c in data["citations"][:8]:
                    st.write(f"- {c['source']} — {c['chunk_id']}: {c['excerpt']}")
        else:
            st.error(r.text)

with col2:
    st.subheader("3) Handbook")
    topic = st.text_input("Handbook topic", value="Retrieval-Augmented Generation")
    target_words = st.number_input("Target words", min_value=2000, max_value=50000, value=20000, step=1000)
    if st.button("Generate Handbook") and doc_id and topic:
        payload = {"document_id": doc_id, "topic": topic, "target_words": int(target_words)}
        r = requests.post(f"{API_BASE}/api/handbook", json=payload, timeout=3600)
        if r.ok:
            data = r.json()
            st.markdown(f"### {data['title']} ({data['word_count']} words)")
            st.download_button("Download Markdown", data["handbook_markdown"], file_name="handbook.md")
            st.markdown("---")
            st.markdown(data["handbook_markdown"])
        else:
            st.error(r.text)
