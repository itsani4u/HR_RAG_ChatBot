# HR Support Chatbot (RAG-Based)

## Overview

This project implements a **Retrieval-Augmented Generation (RAG)** based **HR Support Chatbot** that answers employee questions using official company HR documents.

The chatbot is designed to:

* Provide **accurate, policy-aligned answers**
* Prevent hallucinations by grounding responses in company PDFs
* Support **context-aware follow-up questions**
* Be easily extendable to production-grade HR systems

---

## Key Features

* **PDF-based Knowledge Source** — onboarding, code of conduct, compensation & benefits, leave policy, IT/security policy, workplace safety, etc. (see `documents/`)
* **Retrieval-Augmented Generation (RAG)** — semantic search over HR documents + LLM reasoning
* **Context-Aware Conversations** — supports follow-up questions via chat history
* **Hallucination Control** — if the answer isn't in the documents, the bot says so explicitly
* **Streamlit UI** — simple chat interface suitable for demos and internal tools

---

## Architecture

```
Employee Question
      ↓
Embedding (Gemini gemini-embedding-001)
      ↓
Vector Similarity Search (FAISS)
      ↓
Relevant HR Policy Chunks
      ↓
Prompt Augmentation
      ↓
LLM Answer (Gemini gemini-2.5-flash)
```

---

## Tech Stack

* **Python**
* **Google Gemini API** (via `langchain-google-genai`)
  * `gemini-2.5-flash` (chat model)
  * `gemini-embedding-001` (embedding model)
* **LangChain**
* **FAISS** (vector database)
* **Streamlit** (UI)
* **PyPDF** (PDF ingestion)
* **Docker + Cloud Run** (deployment)

---

## Project Structure

```
hr_rag_chatbot/
│
├── documents/                # Source HR policy PDFs
├── ingest.py                 # One-time PDF ingestion & indexing (Gemini embeddings)
├── chatbot.py                # CLI chatbot (Gemini)
├── app.py                    # Streamlit RAG chatbot (no memory)
├── app_with_memory.py        # Streamlit RAG chatbot (context-aware) — Cloud Run entrypoint
├── requirements.txt
├── .env.example               # Copy to .env for local dev — DO NOT commit real .env
├── Dockerfile                 # Cloud Run container image
├── .dockerignore
├── app.yaml                   # Cloud Run service definition (Knative format)
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

### 3. Build the Vector Index (One-Time / Whenever documents change)

```bash
python ingest.py
```

This loads all PDFs from `documents/`, splits them into chunks, embeds them with
Gemini, and saves a local FAISS index to `hr_faiss_index/`.

> **Note:** The embedding model changed from OpenAI's `text-embedding-3-small`
> to Gemini's `gemini-embedding-001`, which uses a different vector space and
> dimensionality. Any previously-built `hr_faiss_index/` from the OpenAI version
> is **not compatible** — you must re-run `ingest.py` to rebuild it before
> running the chatbot or deploying.

### 4. Run the Chatbot

```bash
# CLI
python chatbot.py

# Streamlit, no memory
streamlit run app.py

# Streamlit, with memory (recommended)
streamlit run app_with_memory.py
```

---

## Deploying to Cloud Run

### 1. Build the index locally first

Cloud Run's filesystem is ephemeral and the container has no Gemini key at
*build* time, so bake a fresh `hr_faiss_index/` into the image by running
`python ingest.py` locally (with `GOOGLE_API_KEY` set) before building.

### 2. Build & push the container image

```bash
export PROJECT_ID=YOUR_PROJECT_ID
export REGION=us-central1

gcloud artifacts repositories create hr-rag-chatbot \
  --repository-format=docker --location=$REGION  # one-time

gcloud auth configure-docker $REGION-docker.pkg.dev

docker build -t $REGION-docker.pkg.dev/$PROJECT_ID/hr-rag-chatbot/hr-rag-chatbot:latest .
docker push $REGION-docker.pkg.dev/$PROJECT_ID/hr-rag-chatbot/hr-rag-chatbot:latest
```

### 3. Store the Gemini key as a Secret Manager secret

```bash
printf "%s" "YOUR_GOOGLE_API_KEY" | gcloud secrets create google-api-key --data-file=-
```

### 4. Deploy

Either with `gcloud run deploy` directly:

```bash
gcloud run deploy hr-rag-chatbot \
  --image=$REGION-docker.pkg.dev/$PROJECT_ID/hr-rag-chatbot/hr-rag-chatbot:latest \
  --region=$REGION \
  --set-secrets=GOOGLE_API_KEY=google-api-key:latest \
  --set-env-vars=MODEL=gemini-2.5-flash,EMBEDDING_MODEL=models/gemini-embedding-001 \
  --allow-unauthenticated
```

or declaratively with the included `app.yaml` (update the `image:` and
`google-api-key` references first):

```bash
gcloud run services replace app.yaml --region=$REGION --project=$PROJECT_ID
gcloud run services add-iam-policy-binding hr-rag-chatbot \
  --region=$REGION --member="allUsers" --role="roles/run.invoker"
```

### 5. Run locally in Docker (optional sanity check)

```bash
docker run -p 8080:8080 --env-file .env $REGION-docker.pkg.dev/$PROJECT_ID/hr-rag-chatbot/hr-rag-chatbot:latest
# open http://localhost:8080
```

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

---

## Limitations

* No role-based access control
* No document citations per answer
* Local FAISS storage baked into the image (not distributed) — rebuilding the
  index means rebuilding and redeploying the container

---

## Disclaimer

This chatbot is intended for **informational purposes only**.
Official HR decisions should always follow company policy and HR approval processes.

---

## License

Internal / Educational Use Only
