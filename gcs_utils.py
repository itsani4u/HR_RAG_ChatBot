"""
Small helpers for moving the FAISS index files through a GCS bucket, since
Cloud Run services are stateless and don't share a local filesystem:

  ingest_service.py  --build_index()-->  local disk  --upload_index_to_gcs()-->  GCS
  app_with_memory.py --download_index_from_gcs()-->  local disk  --> FAISS.load_local()
"""

import os
from google.cloud import storage


def upload_index_to_gcs(local_dir: str, bucket_name: str, prefix: str) -> list:
    client = storage.Client()
    bucket = client.bucket(bucket_name)
    uploaded = []
    for fname in sorted(os.listdir(local_dir)):
        local_path = os.path.join(local_dir, fname)
        if not os.path.isfile(local_path):
            continue
        blob_path = f"{prefix.rstrip('/')}/{fname}"
        bucket.blob(blob_path).upload_from_filename(local_path)
        uploaded.append(f"gs://{bucket_name}/{blob_path}")
    return uploaded


def download_index_from_gcs(bucket_name: str, prefix: str, local_dir: str) -> bool:
    """Returns True if index files were found and downloaded, False otherwise."""
    client = storage.Client()
    bucket = client.bucket(bucket_name)
    blob_prefix = prefix.rstrip("/") + "/"
    blobs = [b for b in bucket.list_blobs(prefix=blob_prefix) if not b.name.endswith("/")]
    if not blobs:
        return False

    os.makedirs(local_dir, exist_ok=True)
    for blob in blobs:
        fname = os.path.basename(blob.name)
        if not fname:
            continue
        blob.download_to_filename(os.path.join(local_dir, fname))
    return True
