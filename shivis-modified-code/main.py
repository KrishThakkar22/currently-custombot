import asyncio
import time
from fastapi import FastAPI, Request, HTTPException
from bs4 import BeautifulSoup
from conversation_manager import ConversationManager
from chatbot_service import ChatbotService
from intercom_service import IntercomService
from config import settings
app = FastAPI()
# --- Global State (Minimized) ---
REPLIED_MESSAGE_IDS = {}
# --- Service Initialization ---
chatbot_service = ChatbotService()
intercom_service = IntercomService()
conversation_manager = ConversationManager(chatbot_service, intercom_service)
# --- API Endpoint ---
@app.post("/query")
async def chat_endpoint(request: Request):
    payload = await request.json()
    try:
        conv_id = payload["data"]["item"]["id"]
        assignee_id = payload["data"]["item"].get("admin_assignee_id")
        msg_id = payload["data"]["item"]["conversation_parts"]["conversation_parts"][-1]["id"]
    except KeyError:
        raise HTTPException(status_code=400, detail="Invalid payload structure")
    if msg_id in REPLIED_MESSAGE_IDS:
        print(f"Already replied to message {msg_id}")
        return {"status": "already_replied"}
    # Extract text from HTML body
    html_body = payload.get("data", {}).get("item", {}).get("conversation_parts", {}).get("conversation_parts", [])[-1].get("body", "") or payload.get("data", {}).get("item", {}).get("source", {}).get("body")
    question = BeautifulSoup(html_body, "html.parser").get_text().strip()
    if not question:
        return {"status": "no_content"}
    # Logic to only respond if assigned to the bot
    if assignee_id == settings.INTERCOM_ADMIN_ID:
        REPLIED_MESSAGE_IDS[msg_id] = time.time()
        await conversation_manager.handle_message(conv_id, question, msg_id)
    return {"status": "ok"}
# --- Background Task ---
async def cleanup_replied_ids():
    while True:
        await asyncio.sleep(600) # Run every 10 minutes
        now = time.time()
        expired_ids = [mid for mid, ts in REPLIED_MESSAGE_IDS.items() if (now - ts) > settings.REPLIED_ID_EXPIRE_SECONDS]
        for mid in expired_ids:
            del REPLIED_MESSAGE_IDS[mid]
        print(f"Cleaned up {len(expired_ids)} expired message IDs.")
@app.on_event("startup")
async def startup_event():
    asyncio.create_task(cleanup_replied_ids())
if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)