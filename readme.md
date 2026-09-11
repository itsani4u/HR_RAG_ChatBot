# HR Support Chatbot (RAG-Based)

## Overview

This project implements a **Retrieval-Augmented Generation (RAG)** based **HR Support Chatbot** that answers employee questions using official company HR documents.

It's split into **two independently deployable Cloud Run services**:

* **`hr-rag-ingest`** — an API you call (manually or on a schedule) to rebuild the FAISS index from the HR PDFs and publish it to a GCS bucket.
* **`hr-rag-chatbot`** — the Streamlit chat UI. On cold start it downloads the latest index from that GCS bucket and serves employee questions.

They don't share a filesystem (Cloud Run instances are stateless/ephemeral), so GCS is the handoff point between them.

---

## Key Features

* **PDF-based Knowledge Source** — onboarding, code of conduct, compensation & benefits, leave policy, IT/security policy, workplace safety, etc. (see `documents/`)
* **Retrieval-Augmented Generation (RAG)** — semantic search over HR documents + LLM reasoning
* **Context-Aware Conversations** — supports follow-up questions via chat history
* **Hallucination Control** — if the answer isn't in the documents, the bot says so explicitly
* **Streamlit UI** — simple chat interface suitable for demos and internal tools
* **Ingest as its own API** — rebuild the knowledge base without redeploying or restarting the chatbot

---

## Architecture

```
                    ┌───────────────────────────┐
  POST /ingest  ──▶ │   hr-rag-ingest (Cloud Run)│
 (you / scheduler)  │   PDFs → chunks → Gemini    │
                    │   embeddings → FAISS index   │
                    └──────────────┬────────────┘
                                   │ upload
                                   ▼
                         gs://YOUR_BUCKET/hr_faiss_index/
                                   │ download (cold start)
                                   ▼
                    ┌───────────────────────────┐
  Employee  ───────▶│  hr-rag-chatbot (Cloud Run)│
  Question           │  FAISS search → Gemini chat│
                    └───────────────────────────┘
```

---

## Tech Stack

* **Python**
* **Google Gemini API** (via `langchain-google-genai`)
  * `gemini-2.5-flash` (chat model)
  * `gemini-embedding-001` (embedding model)
* **LangChain**
* **FAISS** (vector database)
* **Streamlit** (chatbot UI)
* **FastAPI + Uvicorn** (ingest API)
* **Google Cloud Storage** (index handoff between the two services)
* **Docker + Cloud Run** (deployment)

---

## Project Structure

```
hr_rag_chatbot/
│
├── documents/                # Source HR policy PDFs (baked into the ingest image)
├── ingest_core.py             # Shared logic: PDFs → chunks → Gemini embeddings → FAISS
├── gcs_utils.py                # Upload/download the FAISS index to/from GCS
├── ingest.py                   # CLI wrapper around ingest_core (local-only, no GCS)
├── ingest_service.py           # FastAPI "ingest API" — POST /ingest — Cloud Run service #1
├── chatbot.py                  # CLI chatbot (Gemini, local index only)
├── app.py                      # Streamlit RAG chatbot (no memory)
├── app_with_memory.py          # Streamlit RAG chatbot (context-aware) — Cloud Run service #2 entrypoint
├── requirements.txt
├── .env.example                  # Copy to .env for local dev — DO NOT commit a real .env
├── Dockerfile                    # Image for hr-rag-chatbot
├── Dockerfile.ingest              # Image for hr-rag-ingest
├── .dockerignore
├── app.yaml                       # Cloud Run service definition — chatbot
├── ingest.yaml                    # Cloud Run service definition — ingest API
└── readme.md
```

---

## Setup Instructions (Local)

### 1. Install Dependencies

```bash
pip install -r requirements.txt
```

### 2. Configure Environment Variables

```bash
cp .env.example .env
# then edit .env and set GOOGLE_API_KEY (from https://aistudio.google.com/app/apikey)
```

### 3. Build the Vector Index (Local, One-Time / Whenever documents change)

```bash
python ingest.py
```

This loads all PDFs from `documents/`, splits them into chunks, embeds them with
Gemini, and saves a local FAISS index to `hr_faiss_index/`. This is the
local-only path (no GCS) — good for quick iteration.

> **Note:** The embedding model changed from OpenAI's `text-embedding-3-small`
> to Gemini's `gemini-embedding-001`, a different vector space and
> dimensionality. Any old `hr_faiss_index/` built with OpenAI embeddings is
> **not compatible** — rebuild it.

### 4. Run the Chatbot Locally

```bash
# CLI
python chatbot.py

# Streamlit, no memory
streamlit run app.py

# Streamlit, with memory (recommended)
streamlit run app_with_memory.py
```

### 5. Run the Ingest API Locally (optional)

```bash
export GCS_BUCKET=your-bucket-name   # needs `gcloud auth application-default login`
uvicorn ingest_service:app --reload --port 8080
curl -X POST http://localhost:8080/ingest
```

---

## Deploying to Cloud Run (Two Services)

### 1. One-time GCP setup

```bash
export PROJECT_ID=YOUR_PROJECT_ID
export REGION=us-central1
export BUCKET=your-bucket-name

gcloud artifacts repositories create hr-rag-chatbot \
  --repository-format=docker --location=$REGION
gcloud auth configure-docker $REGION-docker.pkg.dev

gsutil mb -l $REGION gs://$BUCKET

printf "%s" "YOUR_GOOGLE_API_KEY" | gcloud secrets create google-api-key --data-file=-

# Grant the default compute service account access to the secret and bucket
export SA="$(gcloud projects describe $PROJECT_ID --format='value(projectNumber)')-compute@developer.gserviceaccount.com"
gcloud secrets add-iam-policy-binding google-api-key \
  --member="serviceAccount:$SA" --role="roles/secretmanager.secretAccessor"
gcloud projects add-iam-policy-binding $PROJECT_ID \
  --member="serviceAccount:$SA" --role="roles/storage.objectAdmin"
```

### 2. Build & push both images

```bash
docker build -f Dockerfile -t $REGION-docker.pkg.dev/$PROJECT_ID/hr-rag-chatbot/hr-rag-chatbot:latest .
docker push $REGION-docker.pkg.dev/$PROJECT_ID/hr-rag-chatbot/hr-rag-chatbot:latest

docker build -f Dockerfile.ingest -t $REGION-docker.pkg.dev/$PROJECT_ID/hr-rag-chatbot/hr-rag-ingest:latest .
docker push $REGION-docker.pkg.dev/$PROJECT_ID/hr-rag-chatbot/hr-rag-ingest:latest
```

### 3. Deploy the ingest API (kept private)

```bash
gcloud run deploy hr-rag-ingest \
  --image=$REGION-docker.pkg.dev/$PROJECT_ID/hr-rag-chatbot/hr-rag-ingest:latest \
  --region=$REGION \
  --set-secrets=GOOGLE_API_KEY=google-api-key:latest \
  --set-env-vars=GCS_BUCKET=$BUCKET,GCS_INDEX_PREFIX=hr_faiss_index,EMBEDDING_MODEL=models/gemini-embedding-001 \
  --no-allow-unauthenticated
```

(or `gcloud run services replace ingest.yaml` after filling in the placeholders)

### 4. Trigger ingestion — build the index at least once before the chatbot needs it

```bash
TOKEN=$(gcloud auth print-identity-token)
INGEST_URL=$(gcloud run services describe hr-rag-ingest --region=$REGION --format='value(status.url)')
curl -X POST -H "Authorization: Bearer $TOKEN" "$INGEST_URL/ingest"
```

Re-run this (or wire it to Cloud Scheduler) any time the PDFs in `documents/`
change and you rebuild/redeploy the ingest image.

### 5. Deploy the chatbot

```bash
gcloud run deploy hr-rag-chatbot \
  --image=$REGION-docker.pkg.dev/$PROJECT_ID/hr-rag-chatbot/hr-rag-chatbot:latest \
  --region=$REGION \
  --set-secrets=GOOGLE_API_KEY=google-api-key:latest \
  --set-env-vars=MODEL=gemini-2.5-flash,EMBEDDING_MODEL=models/gemini-embedding-001,GCS_BUCKET=$BUCKET,GCS_INDEX_PREFIX=hr_faiss_index \
  --allow-unauthenticated
```

(or `gcloud run services replace app.yaml` after filling in the placeholders)

The chatbot downloads the index from `gs://$BUCKET/hr_faiss_index/` on its
first request and caches it in memory for the life of that instance.

---

## Example Questions

```
What is the onboarding process for new employees?
How many leave days am I entitled to?
Can unused leave be carried forward?
What is the IT security policy on passwords?
What should I do in case of a workplace safety incident?
```

---

## Memory Handling

* Chat history is stored in Streamlit session state
* Previous turns are included in the prompt to support follow-ups
* Retrieval is always performed using the **latest question only** to avoid noise

---

## Design Principles

* **LLM does not act as the source of truth** — HR documents are the authority
* **Retrieval before generation** — answers are grounded in retrieved policy text
* **Fail-safe behavior** — the chatbot refuses to answer when information is missing
* **Ingest decoupled from serving** — rebuilding the knowledge base never requires redeploying or restarting the chatbot

---

## Limitations

* No role-based access control
* No document citations per answer
* Chatbot instances cache the index in memory only — a fresh cold start re-downloads from GCS
* No auth on the chatbot by default (`--allow-unauthenticated`) — restrict this for real HR data

---

## Disclaimer

This chatbot is intended for **informational purposes only**.
Official HR decisions should always follow company policy and HR approval processes.

---

## License

Internal / Educational Use Only
