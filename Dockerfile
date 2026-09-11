# HR RAG Chatbot UI - Cloud Run image
# (the ingest API is a separate service/image — see Dockerfile.ingest)
FROM python:3.11-slim

# System deps needed by faiss-cpu / pypdf wheels
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install Python dependencies first (better layer caching)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code, documents, and (pre-built) vector index
COPY . .

# Cloud Run sets $PORT at runtime; default to 8080 for local `docker run`
ENV PORT=8080
EXPOSE 8080

# Streamlit must bind to 0.0.0.0:$PORT and run headless for Cloud Run
CMD streamlit run app_with_memory.py \
    --server.port=${PORT} \
    --server.address=0.0.0.0 \
    --server.headless=true \
    --server.enableCORS=false \
    --server.enableXsrfProtection=false
