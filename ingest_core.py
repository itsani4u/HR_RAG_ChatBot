"""
Core ingestion logic shared by:
  - ingest.py          (local/CLI one-off run)
  - ingest_service.py  (Cloud Run "ingest API", triggered separately from the chatbot)
"""

import os
from langchain_community.document_loaders import PyPDFLoader
from langchain_classic.text_splitter import RecursiveCharacterTextSplitter
from langchain_google_genai import GoogleGenerativeAIEmbeddings
from langchain_community.vectorstores import FAISS

DATA_FOLDER = os.getenv("DATA_FOLDER", "documents")
VECTOR_DB_PATH = os.getenv("VECTOR_DB_PATH", "hr_faiss_index")
EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "models/gemini-embedding-001")


def build_index() -> dict:
    """
    Load PDFs from DATA_FOLDER, chunk them, embed with Gemini, and save a
    local FAISS index to VECTOR_DB_PATH. Returns stats. Does not touch GCS —
    callers decide whether/how to publish the resulting index files.
    """
    if not os.path.isdir(DATA_FOLDER):
        raise RuntimeError(f"Documents folder '{DATA_FOLDER}' not found")

    documents = []
    for file in sorted(os.listdir(DATA_FOLDER)):
        if file.endswith(".pdf"):
            loader = PyPDFLoader(os.path.join(DATA_FOLDER, file))
            documents.extend(loader.load())

    if not documents:
        raise RuntimeError(f"No PDFs found in '{DATA_FOLDER}'")

    text_splitter = RecursiveCharacterTextSplitter(chunk_size=800, chunk_overlap=150)
    chunks = text_splitter.split_documents(documents)

    embeddings = GoogleGenerativeAIEmbeddings(
        model=EMBEDDING_MODEL,
        google_api_key=os.environ["GOOGLE_API_KEY"],
    )

    vectorstore = FAISS.from_documents(chunks, embeddings)
    vectorstore.save_local(VECTOR_DB_PATH)

    return {
        "pages_loaded": len(documents),
        "chunks_created": len(chunks),
        "vector_db_path": VECTOR_DB_PATH,
    }
