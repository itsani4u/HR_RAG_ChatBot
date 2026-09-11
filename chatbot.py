import os
from dotenv import load_dotenv
from langchain_google_genai import ChatGoogleGenerativeAI, GoogleGenerativeAIEmbeddings
from langchain_community.vectorstores import FAISS
from langchain.prompts import ChatPromptTemplate

# -----------------------------------------
# ENV
# -----------------------------------------
load_dotenv()

VECTOR_DB_PATH = "hr_faiss_index"
EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "models/gemini-embedding-001")
CHAT_MODEL = os.getenv("MODEL", "gemini-2.5-flash")

# -----------------------------------------
# LOAD VECTOR DB
# -----------------------------------------
embeddings = GoogleGenerativeAIEmbeddings(model=EMBEDDING_MODEL)
vectorstore = FAISS.load_local(
    VECTOR_DB_PATH,
    embeddings,
    allow_dangerous_deserialization=True
)

retriever = vectorstore.as_retriever(search_kwargs={"k": 4})

# -----------------------------------------
# LLM (Gemini)
# -----------------------------------------
llm = ChatGoogleGenerativeAI(
    model=CHAT_MODEL,
    temperature=0
)

# -----------------------------------------
# PROMPT
# -----------------------------------------
prompt = ChatPromptTemplate.from_template("""
You are an HR Support Assistant.

Answer employee questions using ONLY the provided company documents.
If the answer is not found in the documents, say:
"I'm not sure based on current HR policies."

Be clear, professional, and policy-aligned.

HR Context:
{context}

Employee Question:
{question}
""")

# -----------------------------------------
# CHAT LOOP
# -----------------------------------------
def chat():
    print("\nHR Support Chatbot (type 'exit' to quit)\n")

    while True:
        question = input("Employee: ")
        if question.lower() == "exit":
            break

        docs = retriever.invoke(question)
        context = "\n\n".join(doc.page_content for doc in docs)

        response = llm.invoke(
            prompt.format_messages(
                context=context,
                question=question
            )
        )

        print("\nHR Bot:", response.content)
        print("-" * 60)


if __name__ == "__main__":
    chat()
