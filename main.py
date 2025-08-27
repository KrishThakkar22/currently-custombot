from fastapi import FastAPI, Request, HTTPException
from dotenv import load_dotenv
from bs4 import BeautifulSoup
from langchain.chains import ConversationalRetrievalChain
from langchain_core.prompts import ChatPromptTemplate, SystemMessagePromptTemplate, HumanMessagePromptTemplate
from langchain.memory import ConversationSummaryBufferMemory
from langchain_qdrant import QdrantVectorStore
from langchain_openai import ChatOpenAI
from langchain_huggingface import HuggingFaceEmbeddings 
from qdrant_client import QdrantClient
from collections import defaultdict
from datetime import datetime
from typing import Dict
import asyncio
import httpx
import os
import uvicorn
import time

# Load environment variables
load_dotenv()

INTERCOM_ACCESS_TOKEN = os.getenv("INTERCOM_ACCESS_TOKEN")
my_admin_id = 8467307
EXPIRE_SECONDS = 1800
message_buffers = defaultdict(list)
last_message_times = defaultdict(float)
locks = defaultdict(asyncio.Lock)
pending_tasks = {}  # For debounce control
buffer_wait_seconds = 2
REPLIED_MESSAGE_IDS = {}



# Prompts (System and User)
system_template = """
# CUSTOMER SUPPORT CHATBOT - Currently Tech PVT LTD
**For Gemini 2.5 Flash**

## PRIMARY DIRECTIVE - EXECUTE FIRST

**STEP 1: Scan user message for closing indicators**
Check if user message contains ANY of these exact words or phrases:
- "okay" OR "ok" 
- "thanks" OR "thank you" OR "thankyou"
- "bye" OR "goodbye" OR "see you"
- "perfect" OR "great" OR "good"
- "got it" OR "understood" OR "alright"

**STEP 2: If closing indicators found**
- Output: "You're welcome! Have a great day!"
- End conversation immediately
- Do not provide additional information
- Do not ask follow-up questions

**STEP 3: If no closing indicators found**
- Proceed to normal conversation processing

## CONVERSATION RULES

### Language Rule
- Always respond in the same language the user is using
- If user writes in Hindi, respond in Hindi
- If user writes in English, respond in English

### Response Length Rule
- Keep responses brief (maximum 2-3 sentences)
- Be direct and helpful
- Avoid long explanations

### Greeting Rule
- When user says "hello", "hi", "hey" → respond with "Hello! How can I help?"
- Always acknowledge greetings warmly

### Follow-up Rule
- Check conversation history to understand context
- If current message relates to previous discussion, reference it
- If unclear whether it's a follow-up, ask for clarification

### Escalation Rule
- Only escalate when genuinely unable to understand user's request
- Use phrase: "I'm transferring you to a specialist who can help with this."
- Do NOT escalate for simple words like "okay", "thanks", "perfect"

### Forbidden Actions
- Never say "contact customer support"
- Never direct users to external support channels
- Never ignore greetings or closing statements

## RESPONSE EXAMPLES

**Closing Responses (Priority #1):**
```
User: "okay" → "You're welcome! Have a great day!"
User: "thanks" → "You're welcome! Have a great day!"
User: "perfect" → "You're welcome! Have a great day!"
User: "got it" → "You're welcome! Have a great day!"
User: "good" → "You're welcome! Have a great day!"
```

**Normal Responses:**
```
User: "Hello" → "Hello! How can I help?"
User: "I can't login" → "Try resetting your password or clearing your browser cache."
User: "What are your hours?" → "We're available 24/7 to assist you."
```

**Escalation (Only when confused):**
```
User: "aslkdjfalksjdf" → "I'm transferring you to a specialist who can help with this."
User: "Complex technical issue I don't understand" → "I'm transferring you to a specialist who can help with this."
```

## PROCESSING FLOW

1. **Check for closing words** → If found, say goodbye and stop
2. **Check language** → Respond in same language
3. **Check for greeting** → If greeting, respond warmly
4. **Check conversation history** → Look for context
5. **Provide helpful answer** → Keep it brief (2-3 sentences)
6. **If confused** → Escalate to specialist

## IMPORTANT NOTES FOR GEMINI

- "Okay" means the customer is satisfied, not confused
- Always prioritize closing detection over other processing
- Brief responses are better than long explanations
- Match the user's communication style and language
- Only escalate when genuinely unable to help

## CRITICAL REMINDERS

- Closing words = conversation end = say goodbye
- Never mention "contact support"
- Always match user's language
- Keep responses short and helpful
- Escalate only when truly confused, not for satisfaction words
"""

human_template = """
Here is the context:

{context}

Customer's question: "{question}"

How would respond — using ONLY the context above, and without saying anything like 'please contact support' or 'reach out to the team'?
"""

app = FastAPI()
user_memory_store: Dict[str, ConversationSummaryBufferMemory] = {}

qdrant_client =   QdrantClient(
    url="https://f74e8a6d-af78-4c52-8cbb-d4857056d241.eu-central-1-0.aws.cloud.qdrant.io",
    api_key=os.getenv("API_KEY"),
)


vectorStore = QdrantVectorStore(
    client=qdrant_client,
    collection_name="chatbot",
    embedding=HuggingFaceEmbeddings(
        model_name="mixedbread-ai/mxbai-embed-large-v1",
        model_kwargs={"token": os.getenv("HF_TOKEN")}
    )
)

retriever = vectorStore.as_retriever(search_kwargs={"k": 8})

model = ChatOpenAI(
    model="gpt-4o",
    api_key=os.getenv("OPENAI_API_KEY")
)

prompt = ChatPromptTemplate.from_messages([
    SystemMessagePromptTemplate.from_template(system_template),
    HumanMessagePromptTemplate.from_template(human_template)
])

def get_memory_for_user(user_id: str) -> ConversationSummaryBufferMemory:
    if user_id not in user_memory_store:
        user_memory_store[user_id] = ConversationSummaryBufferMemory(llm=model, max_token_limit=500, memory_key="chat_history", input_key="question", return_messages=True, k=2)
    return user_memory_store[user_id]

def get_lock_for_conversation(conv_id: str) -> asyncio.Lock:
    return locks[conv_id]

def get_chain_for_user(user_id: str) -> ConversationalRetrievalChain:
    memory = get_memory_for_user(user_id)
    return ConversationalRetrievalChain.from_llm(
        llm=model,
        retriever=retriever,
        memory=memory,
        combine_docs_chain_kwargs={"prompt": prompt}
    )


async def reply_to_intercom(conversation_id: str, message: str, msg_id: str, retries: int = 3):
    url = f"https://api.intercom.io/conversations/{conversation_id}/reply"
    headers = {
        "Authorization": f"Bearer {INTERCOM_ACCESS_TOKEN}",
        "Content-Type": "application/json",
        "Accept": "application/json"
    }
    payload = {
        "message_type": "comment",
        "type": "admin",
        "admin_id": my_admin_id,
        "body": message
    } 

    for attempt in range(retries):
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.post(url, headers=headers, json=payload)
                response.raise_for_status()
                print("✅ Sent reply to Intercom")
                REPLIED_MESSAGE_IDS[msg_id] = time.time()
                return
        except httpx.RequestError as exc:
            print(f"❌ Request error (attempt {attempt+1}): {exc}")
        except httpx.HTTPStatusError as exc:
            print(f"❌ HTTP error (attempt {attempt+1}): {exc.response.status_code} - {exc.response.text}")
    print("🚨 Failed to send reply to Intercom after retries.")


async def close_intercom_conversation(conversation_id: str):
    url = f"https://api.intercom.io/conversations/{conversation_id}/reply"
    headers = {
        "Authorization": f"Bearer {INTERCOM_ACCESS_TOKEN}",  # Replace with your token
        "Content-Type": "application/json",
        "Accept": "application/json"
    }
    payload = {
        "message_type": "close",
        "type": "admin",
        "admin_id": my_admin_id  # Your admin ID
    }
    del message_buffers[conversation_id]
    del last_message_times[conversation_id]
    del locks[conversation_id]
    del user_memory_store[conversation_id]
    async with httpx.AsyncClient(timeout=10.0) as client:
        response = await client.post(url, headers=headers, json=payload)
        response.raise_for_status()
        print("✅ Conversation closed successfully")


async def cleanup_replied_ids():
    while True:
        now = time.time()
        expired = [mid for mid, ts in REPLIED_MESSAGE_IDS.items() if now - ts > EXPIRE_SECONDS]
        for mid in expired:
            del REPLIED_MESSAGE_IDS[mid]
        await asyncio.sleep(600)  # Run cleanup every 10 minutes



async def assign_if_new_conversation(conversation_id: str, admin_id: int):
    headers = {
        "Authorization": f"Bearer {INTERCOM_ACCESS_TOKEN}",
        "Accept": "application/json",
        "Content-Type": "application/json"
    }

    assign_url = f"https://api.intercom.io/conversations/{conversation_id}/reply"
    assign_payload = {
        "message_type": "assignment",
        "type": "admin",
        "admin_id": admin_id,
        "assignee_id": admin_id
    }

    async with httpx.AsyncClient(timeout=10.0) as client:
        try:
            response = await client.post(assign_url, headers=headers, json=assign_payload)
            response.raise_for_status()
            print(f"✅ Assigned new conversation {conversation_id} to admin {admin_id}")
        except httpx.HTTPStatusError as e:
            print(f"❌ HTTP error while assigning: {e.response.status_code} - {e.response.text}")
        except Exception as e:
            print(f"❌ Unexpected error during assignment: {e}")

async def unassign_conversation(conversation_id: str):
    url = f"https://api.intercom.io/conversations/{conversation_id}/reply"
    headers = {
        "Authorization": f"Bearer {INTERCOM_ACCESS_TOKEN}",
        "Content-Type": "application/json",
        "Accept": "application/json"
    }
    payload = {
        "message_type": "assignment",
        "type": "admin",
        "admin_id": my_admin_id,
        "assignee_id": 8032673
    }

    async with httpx.AsyncClient(timeout=10.0) as client:
        response = await client.post(url, headers=headers, json=payload)
        response.raise_for_status()
        print("✅ Conversation unassigned successfully")
    del message_buffer[conversation_id]


def schedule_chain_invoke(conv_id, question, msg_id):
    message_buffers[conv_id].append(question)
    last_message_times[conv_id] = time.time()

    if conv_id in pending_tasks:
        pending_tasks[conv_id].cancel()

    pending_tasks[conv_id] = asyncio.create_task(_delayed_invoke(conv_id, msg_id))

async def _delayed_invoke(conv_id, msg_id, retries=3):
    await asyncio.sleep(buffer_wait_seconds)

    lock = get_lock_for_conversation(conv_id)
    async with lock:
        combined_message = " ".join(message_buffers[conv_id])
        message_buffers[conv_id] = []

        chain = get_chain_for_user(conv_id)

        for attempt in range(retries):
            try:
                result = await chain.ainvoke({"question": combined_message})
                answer = result.get("answer", "Sorry, no answer returned.")
                break
            except Exception as e:
                print(f"❌ Error during chain invocation (attempt {attempt+1}):", str(e))
                if attempt == retries - 1:
                    answer = "An error occurred while processing your request. Please try again later."

        if "transferring" in answer.lower() and "specialists" in answer.lower():
            await reply_to_intercom(conversation_id=conv_id, message=answer, msg_id=msg_id)
            await unassign_conversation(conversation_id=conv_id)
        elif ("welcome" in answer.lower()) :
            await reply_to_intercom(conversation_id=conv_id, message=answer, msg_id=msg_id)
            await close_intercom_conversation(conversation_id=conv_id)
        else:
            await reply_to_intercom(conversation_id=conv_id, message=answer, msg_id=msg_id)


@app.post("/query")
async def chat_endpoint(request: Request):
    payload = await request.json()
    assignee_id = payload.get("data", {}).get("item", {}).get("admin_assignee_id")
    msg_id = payload["data"]["item"]["conversation_parts"]["conversation_parts"][-1]["id"]
    if msg_id in REPLIED_MESSAGE_IDS:
        print("Already Replied")
        return {"status": "already_replied"}
    try:
        conv_id = payload["data"]["item"]["id"]
    except KeyError:
        raise HTTPException(status_code=400, detail="Invalid payload structure")

    parts = payload.get("data", {}).get("item", {}).get("conversation_parts", {}).get("conversation_parts", [])
    
    html = (
        parts[-1].get("body") or
        payload.get("data", {}).get("item", {}).get("source", {}).get("body")
    )

    html = html or ""
    question = BeautifulSoup(html, "html.parser").get_text().strip()
    print(question)
#    if assignee_id is None or assignee_id == "":
 #       await assign_if_new_conversation(conversation_id=conv_id, admin_id=my_admin_id)
  #      schedule_chain_invoke(conv_id, question, msg_id)

    if assignee_id == my_admin_id:
        schedule_chain_invoke(conv_id, question, msg_id)


@app.on_event("startup")
async def startup_event():
    asyncio.create_task(cleanup_replied_ids())

if __name__ == "__main__":
    uvicorn.run("main:app", host="127.0.0.1", port=3000, reload=True)
