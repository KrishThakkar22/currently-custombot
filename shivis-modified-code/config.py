import os
from dotenv import load_dotenv

load_dotenv()

class Settings:
    # Intercom Settings
    INTERCOM_TOKEN: str = os.getenv("INTERCOM_TOKEN") # It's better to load this from .env
    INTERCOM_ADMIN_ID: int = 8467307
    INTERCOM_SPECIALIST_ID: int = 8032673 # The ID to unassign to

    # Qdrant Settings
    QDRANT_URL: str = os.getenv("QDRANT_URL", "https://f74e8a6d-af78-4c52-8cbb-d4857056d241.eu-central-1-0.aws.cloud.qdrant.io")
    QDRANT_API_KEY: str = os.getenv("API_KEY")
    QDRANT_COLLECTION_NAME: str = "chatbot"

    # Model Settings
    OPENAI_API_KEY: str = os.getenv("OPENAI_API_KEY")
    EMBEDDING_MODEL: str = "mixedbread-ai/mxbai-embed-large-v1"
    LLM_MODEL: str = "gpt-4o-mini"
    HF_TOKEN: str = os.getenv("HF_TOKEN")

    # Application Settings
    BUFFER_WAIT_SECONDS: int = 2
    REPLIED_ID_EXPIRE_SECONDS: int = 1800

# Create a single instance to be imported elsewhere
settings = Settings()