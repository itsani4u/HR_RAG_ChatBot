"""
Local/manual ingestion run: `python ingest.py`.

Builds the FAISS index on local disk only. For the Cloud Run deployment, use
ingest_service.py instead (deployed as its own service, publishes to GCS) —
see readme.md.
"""

from dotenv import load_dotenv

from ingest_core import build_index

load_dotenv()

if __name__ == "__main__":
    stats = build_index()
    print(f"Loaded {stats['pages_loaded']} pages from PDFs")
    print(f"Created {stats['chunks_created']} text chunks")
    print(f"HR knowledge base successfully indexed at '{stats['vector_db_path']}'")
