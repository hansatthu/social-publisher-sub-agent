import httpx
import json
import logging

logger = logging.getLogger(__name__)

OLLAMA_URL = "http://ollama:11434/api/generate"
MODEL_NAME = "llama3.2:3b"

SYSTEM_PROMPT = """Bạn là một bộ phân loại ý định (Intent Router).
Nhiệm vụ của bạn là phân loại tin nhắn của người dùng thành 1 trong 3 nhãn:
- GREETING: Lời chào hỏi thông thường.
- PURCHASE: Yêu cầu mua hàng, hỏi giá, sản phẩm.
- SPAM: Tin nhắn rác, không có ý nghĩa.

Chỉ trả về ĐÚNG 1 JSON object có định dạng sau, tuyệt đối không có văn bản nào khác:
{"intent": "GREETING" | "PURCHASE" | "SPAM"}
"""

async def classify_intent(message: str) -> dict:
    payload = {
        "model": MODEL_NAME,
        "prompt": message,
        "system": SYSTEM_PROMPT,
        "stream": False,
        "format": "json"
    }
    
    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.post(OLLAMA_URL, json=payload)
            response.raise_for_status()
            result = response.json()
            
            # Trích xuất JSON từ phản hồi của Ollama
            response_text = result.get("response", "{}")
            intent_data = json.loads(response_text)
            
            intent = intent_data.get("intent", "SPAM")
            return {"intent": intent}
    except Exception as e:
        logger.error(f"Error calling Ollama: {str(e)}")
        # Fallback an toàn nếu LLM lỗi
        return {"intent": "SPAM"}

def handle_intent(intent: str, message: str) -> dict:
    # Luôn luôn chuyển cho Master Agent (DeepSeek) xử lý
    # Bỏ qua giới hạn GREETING/SPAM/PURCHASE cứng ngắc cũ.
    return {"reply": "Đang chuyển cho Master Agent...", "route": "CORE_AGENT"}
