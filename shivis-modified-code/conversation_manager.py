import asyncio
import time
from langchain.memory import ConversationSummaryBufferMemory
from chatbot_service import ChatbotService
from intercom_service import IntercomService
from config import settings

CLOSING_KEYWORDS = ["ok", "okay", "thanks", "thank you", "thankyou",
                    "bye", "goodbye", "see you",
                    "perfect", "great", "good",
                    "got it", "understood", "alright"]



class Conversation:
    """Represents the state of a single conversation."""
    def __init__(self, conv_id: str, llm):
        self.id = conv_id
        self.message_buffer = []
        self.last_message_time = 0.0
        self.lock = asyncio.Lock()
        self.pending_task = None
        self.memory = ConversationSummaryBufferMemory(
            llm=llm,
            max_token_limit=500,
            memory_key="chat_history",
            input_key="question",
            return_messages=True
        )
class ConversationManager:

    def __init__(self, chatbot_service: ChatbotService, intercom_service: IntercomService):
        self._conversations = {}
        self._chatbot_service = chatbot_service
        self._intercom_service = intercom_service
    
    def _get_or_create_conversation(self, conv_id: str) -> Conversation:
        if conv_id not in self._conversations:
            self._conversations[conv_id] = Conversation(conv_id, self._chatbot_service.model)
        return self._conversations[conv_id]
    
    async def handle_message(self, conv_id: str, question: str, msg_id: str):
        conv = self._get_or_create_conversation(conv_id)
        conv.message_buffer.append(question)
        conv.last_message_time = time.time()
        if conv.pending_task:
            conv.pending_task.cancel()
        conv.pending_task = asyncio.create_task(self._delayed_invoke(conv, msg_id))
    
    async def _delayed_invoke(self, conv: Conversation, msg_id: str):
        await asyncio.sleep(settings.BUFFER_WAIT_SECONDS)
        async with conv.lock:
            if not conv.message_buffer:
                return

            combined_message = " ".join(conv.message_buffer).strip()
            conv.message_buffer = []  # clear early to avoid reprocessing

            try:
                # Closing keyword detection
                if any(kw in combined_message.lower() for kw in CLOSING_KEYWORDS):
                    answer = "You're welcome!"
                else:
                    chain = self._chatbot_service.get_chain(conv.memory)
                    result = await chain.ainvoke({"question": combined_message})
                    answer = result.get("answer", "Sorry, I couldn't process that.")
            except Exception as e:
                print(f":x: Error during chain invocation: {e}")
                answer = "An error occurred. Please try again later."

            # Handle response routing
            ans_lower = answer.lower()
            if "welcome" in ans_lower:
                await self._intercom_service.reply_to_conversation(conv.id, answer)
                await self._intercom_service.close_conversation(conv.id)
                self._conversations.pop(conv.id, None)  # safe cleanup
            elif "specialist" in ans_lower and "transfer" in ans_lower:
                await self._intercom_service.reply_to_conversation(conv.id, answer)
                await self._intercom_service.unassign_conversation(conv.id)
                self._conversations.pop(conv.id, None)
            else:
                await self._intercom_service.reply_to_conversation(conv.id, answer)
