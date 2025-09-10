import os
from dotenv import load_dotenv
from langchain_community.document_loaders import PyPDFLoader
from langchain.text_splitter import RecursiveCharacterTextSplitter
from langchain_qdrant.vectorstores import Qdrant
from qdrant_client import QdrantClient
from langchain_huggingface import HuggingFaceEmbeddings
from langchain_qdrant import QdrantVectorStore
from config import settings
load_dotenv()

# Step 1: Configure Qdrant client
client = QdrantClient(
    url=settings.QDRANT_URL,
    api_key=settings.QDRANT_API_KEY,
)


vectorStore = QdrantVectorStore(
        client=client,
        collection_name=settings.QDRANT_COLLECTION_NAME,
        embedding= HuggingFaceEmbeddings(
            model_name=settings.EMBEDDING_MODEL,
            model_kwargs={"token": settings.HF_TOKEN}
        )
    )

pdf_files = [file for file in os.listdir("../Data-documents") if file.endswith(".pdf") and file.startswith("Community Guidelines and Rules")]
print(f"Found PDF files: {pdf_files}")

all_documents = []

for file in pdf_files:
    loader = PyPDFLoader("../Data-documents/"+file)
    pages = loader.load()
    for page in pages:
        page.metadata["source_file"] = file
    all_documents.extend(pages)

# Step 6: Split text into manageable chunks
text_splitter = RecursiveCharacterTextSplitter(
    chunk_size=800,
    chunk_overlap=200,
)
documents = text_splitter.split_documents(all_documents)

# Step 7: Store into Qdrant
vectorStore.add_documents(documents)

print("✅ Data successfully stored in Qdrant collection 'chatbot'.")