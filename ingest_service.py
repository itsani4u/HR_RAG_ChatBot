"""
Ingest API — a standalone Cloud Run service.

Deployed separately from the chatbot UI. Call POST /ingest whenever the HR
PDFs change to rebuild the FAISS index and publish it to GCS; the chatbot
service picks up the new index on its next cold start (or process restart).

This service is intended to be deployed WITHOUT --allow-unauthenticated —
trigger it with an identity token (see readme.md) so random callers can't
rebuild your knowledge base.
"""

import logging
import os

from fastapi import FastAPI, HTTPException

from gcs_utils import upload_index_to_gcs
from ingest_core import VECTOR_DB_PATH, build_index

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("ingest_service")

app = FastAPI(title="HR RAG Ingest Service")

GCS_BUCKET = os.getenv("GCS_BUCKET")
GCS_INDEX_PREFIX = os.getenv("GCS_INDEX_PREFIX", "hr_faiss_index")


@app.get("/")
def health():
    return {"status": "ok", "service": "hr-rag-ingest"}


@app.post("/ingest")
def ingest():
    if not GCS_BUCKET:
        raise HTTPException(status_code=500, detail="GCS_BUCKET env var is not set")

    try:
        stats = build_index()
        uploaded = upload_index_to_gcs(VECTOR_DB_PATH, GCS_BUCKET, GCS_INDEX_PREFIX)
    except Exception as exc:  # noqa: BLE001
        logger.exception("Ingestion failed")
        raise HTTPException(status_code=500, detail=f"Ingestion failed: {exc}") from exc

    logger.info("Ingestion complete: %s", stats)
    return {
        "status": "success",
        **stats,
        "gcs_bucket": GCS_BUCKET,
        "gcs_prefix": GCS_INDEX_PREFIX,
        "uploaded_files": uploaded,
    }
