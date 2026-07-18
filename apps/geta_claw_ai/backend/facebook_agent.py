import os
import requests
import logging
from typing import Optional
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.messages import HumanMessage, SystemMessage

logger = logging.getLogger(__name__)

def get_gemini_key() -> Optional[str]:
    keys_str = os.getenv("GEMINI_API_KEYS", "")
    if not keys_str:
        return None
    keys = [k.strip() for k in keys_str.split(",") if k.strip()]
    return keys[0] if keys else None

def generate_social_post(page_name: str) -> str:
    """Sinh nội dung bài đăng Facebook tự động bằng AI."""
    api_key = get_gemini_key()
    if not api_key:
        return "Xin chào các bạn! Chúc một ngày tốt lành từ " + page_name
        
    try:
        llm = ChatGoogleGenerativeAI(
            model="gemini-2.5-flash",
            temperature=0.7,
            google_api_key=api_key
        )
        sys_prompt = f"Bạn là chuyên gia Content Marketing của Fanpage '{page_name}'. Hãy viết một bài đăng Facebook ngắn gọn (dưới 150 chữ), thu hút, có chứa emoji. Đừng dùng hashtag quá nhiều."
        msg = HumanMessage(content="Viết một bài đăng tương tác hoặc giới thiệu sản phẩm thật hấp dẫn hôm nay.")
        
        response = llm.invoke([SystemMessage(content=sys_prompt), msg])
        return response.content
    except Exception as e:
        logger.error(f"Error generating post: {e}")
        return f"Chào ngày mới cùng {page_name}! Đừng quên ủng hộ chúng mình nhé ❤️"

def generate_comment_reply(comment_text: str, page_name: str) -> str:
    """Sinh câu trả lời comment của khách hàng bằng AI."""
    api_key = get_gemini_key()
    if not api_key:
        return "Cảm ơn bạn đã quan tâm! Vui lòng inbox fanpage để được hỗ trợ nhé."
        
    try:
        llm = ChatGoogleGenerativeAI(
            model="gemini-2.5-flash",
            temperature=0.5,
            google_api_key=api_key
        )
        sys_prompt = f"Bạn là CSKH thân thiện của Fanpage '{page_name}'. Khách hàng vừa bình luận trên trang của bạn."
        msg = HumanMessage(content=f"Bình luận của khách: '{comment_text}'. Hãy viết một câu trả lời ngắn gọn (1-2 câu), lịch sự và thân thiện.")
        
        response = llm.invoke([SystemMessage(content=sys_prompt), msg])
        return response.content
    except Exception as e:
        logger.error(f"Error generating comment reply: {e}")
        return "Dạ admin đây ạ, cảm ơn bạn nhiều nhé ❤️"

def post_to_facebook(page_id: str, token: str, message: str) -> dict:
    """Đăng bài lên Facebook Page."""
    url = f"https://graph.facebook.com/v19.0/{page_id}/feed"
    payload = {
        "message": message,
        "access_token": token
    }
    try:
        res = requests.post(url, data=payload)
        res.raise_for_status()
        return res.json()
    except Exception as e:
        logger.error(f"Failed to post to facebook page {page_id}: {e}")
        if isinstance(e, requests.exceptions.HTTPError):
            logger.error(f"Response: {e.response.text}")
        return {}

def reply_to_facebook_comment(comment_id: str, token: str, message: str) -> dict:
    """Trả lời một bình luận cụ thể trên Facebook."""
    url = f"https://graph.facebook.com/v19.0/{comment_id}/comments"
    payload = {
        "message": message,
        "access_token": token
    }
    try:
        res = requests.post(url, data=payload)
        res.raise_for_status()
        return res.json()
    except Exception as e:
        logger.error(f"Failed to reply to comment {comment_id}: {e}")
        if isinstance(e, requests.exceptions.HTTPError):
            logger.error(f"Response: {e.response.text}")
        return {}
