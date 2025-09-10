from fastapi import FastAPI, Request, HTTPException
from intercom_service import IntercomService
from config import settings
from datetime import datetime

app = FastAPI()
intercom_service = IntercomService()

@app.post("/closing")
async def closing_chat(request: Request):
    conversation = await request.json()
    print(conversation.get("data").get("item").get("source").get("author").get("name"))

    stats = conversation.get("data").get("item").get("statistics", {})
    conv_id = conversation["data"]["item"]["id"]
    # print(stats)
    # parts = conversation.get("conversation_parts", {}).get("conversation_parts", [])

    last_close_at = stats.get("last_close_at")
    last_admin_reply_at = stats.get("last_admin_reply_at")
    last_contact_reply_at = stats.get("last_contact_reply_at")

    # Normalize: convert ISO8601 to epoch if needed
    def to_epoch(val):
        if not val:
            return None
        if isinstance(val, int):
            return val
        try:
            return int(datetime.fromisoformat(val.replace("Z", "+00:00")).timestamp())
        except Exception:
            return None

    last_close_at = to_epoch(last_close_at)
    last_admin_reply_at = to_epoch(last_admin_reply_at)
    last_contact_reply_at = to_epoch(last_contact_reply_at)

    

    # Case 1: User replied after close and last_admin_reply_at < last_close_at
    if last_close_at and last_contact_reply_at and last_contact_reply_at > last_close_at :
        await intercom_service.assign_conversation(conversation_id=conv_id, admin_id=settings.INTERCOM_ADMIN_ID)
    else:
        print("ongoing Conversation")
    # 
    # await intercom_service.assign_conversation(conversation_id=conv_id, admin_id=settings.INTERCOM_ADMIN_ID)
    # await intercom_service.close_conversation(conversation_id=conv_id)
    # print("Assigned to Bot while Closing the chat")
    # return {"status": "ok"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("test:app", host="0.0.0.0", port=3000, reload=True)