import os
from dotenv import load_dotenv
from langchain_community.document_loaders import PyPDFLoader
from langchain.text_splitter import RecursiveCharacterTextSplitter
from langchain_huggingface import HuggingFaceEmbeddings
from langchain_qdrant.vectorstores import Qdrant
from qdrant_client import QdrantClient
from qdrant_client.http.models import Distance, VectorParams
from config import settings

# Load environment variables (e.g., API key)
load_dotenv()

# Step 1: Set up Qdrant client
client = QdrantClient(
    url=settings.QDRANT_URL,
    api_key=settings.QDRANT_API_KEY,
    timeout=60.0  # Increase timeout
)

# Step 2: Recreate collection (optional if already done)
client.recreate_collection(
    collection_name=settings.QDRANT_COLLECTION_NAME,
    vectors_config=VectorParams(size=1024, distance=Distance.COSINE)
)

# Step 3: Initialize embedding model
embedding = HuggingFaceEmbeddings(
    model_name=settings.EMBEDDING_MODEL,
    model_kwargs={"token": settings.HF_TOKEN}
)

# Step 4: Set up Qdrant Vector Store
qdrant = Qdrant(
    client=client,
    collection_name=settings.QDRANT_COLLECTION_NAME,
    embeddings=embedding
)

# Step 5: Load PDFs
pdf_files = [file for file in os.listdir("../Data-documents") if file.endswith(".pdf")]
print(f"Found PDF files: {pdf_files}")

all_documents = []
for file in pdf_files:
    loader = PyPDFLoader("../Data-documents/"+file)
    pages = loader.load()
    for page in pages:
        page.metadata["source_file"] = file
    all_documents.extend(pages)

# Step 6: Split documents
text_splitter = RecursiveCharacterTextSplitter(chunk_size=800, chunk_overlap=200)
documents = text_splitter.split_documents(all_documents)

# Step 7: Batch upload
def batch_upload(docs, batch_size=50):
    for i in range(0, len(docs), batch_size):
        print(f"Uploading batch {i // batch_size + 1}...")
        qdrant.add_documents(docs[i:i+batch_size])

batch_upload(documents)

print("✅ All documents uploaded successfully to Qdrant.")
