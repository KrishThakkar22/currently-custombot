from langchain.chains import ConversationalRetrievalChain
from langchain_core.prompts import ChatPromptTemplate
from langchain_openai import ChatOpenAI
from langchain_qdrant import QdrantVectorStore
from langchain_huggingface import HuggingFaceEmbeddings
from qdrant_client import QdrantClient
from config import settings
from prompts import SYSTEM_TEMPLATE, HUMAN_TEMPLATE
class ChatbotService:
    def __init__(self):
        self.model = ChatOpenAI(
            model=settings.LLM_MODEL,
            api_key=settings.OPENAI_API_KEY,
            temperature=1,
        )
        self.vector_store = QdrantVectorStore(
            client=QdrantClient(url=settings.QDRANT_URL, api_key=settings.QDRANT_API_KEY),
            collection_name=settings.QDRANT_COLLECTION_NAME,
            embedding=HuggingFaceEmbeddings(
                model_name=settings.EMBEDDING_MODEL,
                model_kwargs={"token": settings.HF_TOKEN}
            )
        )
        self.retriever = self.vector_store.as_retriever(search_kwargs={"k": 8})
        self.prompt = ChatPromptTemplate.from_messages([
            ("system", SYSTEM_TEMPLATE),
            ("human", HUMAN_TEMPLATE)
        ])
    def get_chain(self, memory) -> ConversationalRetrievalChain:
        return ConversationalRetrievalChain.from_llm(
            llm=self.model,
            retriever=self.retriever,
            memory=memory,
            combine_docs_chain_kwargs={"prompt": self.prompt}
        )