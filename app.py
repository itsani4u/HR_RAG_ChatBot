import os
import streamlit as st
from dotenv import load_dotenv

from langchain_google_genai import ChatGoogleGenerativeAI, GoogleGenerativeAIEmbeddings
from langchain_community.vectorstores import FAISS
from langchain.prompts import ChatPromptTemplate

from gcs_utils import download_index_from_gcs

# -----------------------------------------
# ENV SETUP
# -----------------------------------------
load_dotenv()

st.set_page_config(
    page_title="HR Support Chatbot",
    page_icon="💼",
    layout="centered"
)

# -----------------------------------------
# CONSTANTS
# -----------------------------------------
VECTOR_DB_PATH = "hr_faiss_index"
EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "models/gemini-embedding-001")
CHAT_MODEL = os.getenv("MODEL", "gemini-2.5-flash")

# The ingest API (ingest_service.py) is deployed and invoked separately from
# this chatbot. It publishes the FAISS index to GCS; this app pulls it down
# on cold start (or reuses a local copy if one is already on disk).
GCS_BUCKET = os.getenv("GCS_BUCKET")
GCS_INDEX_PREFIX = os.getenv("GCS_INDEX_PREFIX", "hr_faiss_index")

# -----------------------------------------
# LOAD VECTOR STORE (CACHED)
# -----------------------------------------
@st.cache_resource
def load_vectorstore():
    index_file = os.path.join(VECTOR_DB_PATH, "index.faiss")
    if not os.path.exists(index_file):
        if not GCS_BUCKET:
            st.error(
                "No local FAISS index found and GCS_BUCKET is not set. "
                "Run the ingest service first, or run `python ingest.py` locally."
            )
            st.stop()
        found = download_index_from_gcs(GCS_BUCKET, GCS_INDEX_PREFIX, VECTOR_DB_PATH)
        if not found:
            st.error(
                f"No index found at gs://{GCS_BUCKET}/{GCS_INDEX_PREFIX}. "
                "Call the ingest service's /ingest endpoint first."
            )
            st.stop()

    embeddings = GoogleGenerativeAIEmbeddings(model=EMBEDDING_MODEL)
    vectorstore = FAISS.load_local(
        VECTOR_DB_PATH,
        embeddings,
        allow_dangerous_deserialization=True
    )
    return vectorstore

vectorstore = load_vectorstore()
retriever = vectorstore.as_retriever(search_kwargs={"k": 4})

# -----------------------------------------
# LOAD LLM (CACHED)
# -----------------------------------------
@st.cache_resource
def load_llm():
    return ChatGoogleGenerativeAI(
        model=CHAT_MODEL,
        temperature=0
    )

llm = load_llm()

# -----------------------------------------
# PROMPT
# -----------------------------------------
prompt = ChatPromptTemplate.from_template("""
You are an HR Support Assistant for company employees.

Answer questions using ONLY the information provided in the HR documents.
If the answer is not present, say:
"I'm not sure based on current HR policies."

Be clear, professional, and concise.

HR Context:
{context}

Employee Question:
{question}
""")

# -----------------------------------------
# SESSION STATE (CHAT MEMORY)
# -----------------------------------------
if "messages" not in st.session_state:
    st.session_state.messages = []

# -----------------------------------------
# UI
# -----------------------------------------
st.title("HR Support Chatbot")
st.markdown(
    "Ask questions about onboarding, leave policy, compensation, IT usage, "
    "security guidelines, and workplace safety."
)

# Display chat history
for msg in st.session_state.messages:
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])

# -----------------------------------------
# CHAT INPUT
# -----------------------------------------
user_question = st.chat_input("Ask an HR-related question...")

if user_question:
    # Show user message
    st.session_state.messages.append({
        "role": "user",
        "content": user_question
    })

    with st.chat_message("user"):
        st.markdown(user_question)

    with st.spinner("Searching HR policies..."):
        # Retrieve relevant docs
        docs = retriever.invoke(user_question)
        context = "\n\n".join(doc.page_content for doc in docs)

        # LLM response
        response = llm.invoke(
            prompt.format_messages(
                context=context,
                question=user_question
            )
        )

    # Show assistant response
    with st.chat_message("assistant"):
        st.markdown(response.content)

    st.session_state.messages.append({
        "role": "assistant",
        "content": response.content
    })
