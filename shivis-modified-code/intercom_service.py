import httpx
from config import settings
import datetime
class IntercomService:
    def __init__(self):
        self.base_url = "https://api.intercom.io"
        self.headers = {
            "Authorization": f"Bearer {settings.INTERCOM_TOKEN}",
            "Content-Type": "application/json",
            "Accept": "application/json"
        }
    async def _send_request(self, method: str, url: str, json: dict):
        async with httpx.AsyncClient(timeout=10.0) as client:
            try:
                response = await client.request(method, url, headers=self.headers, json=json)
                response.raise_for_status()
                return response.json()
            except httpx.HTTPStatusError as e:
                print(f":x: HTTP error: {e.response.status_code} - {e.response.text}")
            except httpx.RequestError as e:
                print(f":x: Request error: {e}")
            return None
    async def reply_to_conversation(self, conversation_id: str, message: str):
        url = f"{self.base_url}/conversations/{conversation_id}/reply"
        payload = {
            "message_type": "comment",
            "type": "admin",
            "admin_id": settings.INTERCOM_ADMIN_ID,
            "body": message
        }
        await self._send_request("POST", url, payload)
        print(f":white_check_mark: Sent reply to conversation {conversation_id}")
    async def close_conversation(self, conversation_id: str):
        url = f"{self.base_url}/conversations/{conversation_id}/reply"
        payload = {
            "message_type": "close",
            "type": "admin",
            "admin_id": settings.INTERCOM_ADMIN_ID
        }
        await self._send_request("POST", url, payload)
        print(f":white_check_mark: Closed conversation {conversation_id}")
    async def assign_conversation(self, conversation_id: str, admin_id: int):
        # This function needs to be fully implemented if you plan to use it
        url = f"{self.base_url}/conversations/{conversation_id}/reply"
        payload = {
            "message_type": "assignment",
            "type": "admin",
            "admin_id": settings.INTERCOM_ADMIN_ID,
            "assignee_id": admin_id
        }
        await self._send_request("POST", url, payload)
        print(f":white_check_mark: Assigned conversation {conversation_id} to admin {admin_id}")
    async def unassign_conversation(self, conversation_id: str):
        url = f"{self.base_url}/conversations/{conversation_id}/reply"

        now = datetime.datetime.now()
        current_time = now.time()
        if current_time < settings.THRESHOLD:
            payload = {
                "message_type": "assignment",
                "type": "admin",
                "admin_id": settings.INTERCOM_ADMIN_ID,
                "assignee_id": settings.INTERCOM_SPECIALIST_ID
            }
            await self._send_request("POST", url, payload)
            print(f":white_check_mark: Unassigned conversation {conversation_id} to REENA")
        else:
            payload = {
                "message_type": "assignment",
                "type": "admin",
                "admin_id": settings.INTERCOM_ADMIN_ID,
                "assignee_id": settings.INTERCOM_SPECIALIST_ID_2
            }
            await self._send_request("POST", url, payload)
            print(f":white_check_mark: Unassigned conversation {conversation_id} to NIKHIL")
        