import os
from langchain_openai import ChatOpenAI
from langchain_core.messages import SystemMessage, HumanMessage

def generate_tiktok_script(topic: str, duration_seconds: int = 30) -> str:
    """Sinh kịch bản TikTok tối ưu cho TTS.
    Trung bình 3 từ/giây. Thời lượng được tuỳ chỉnh bởi duration_seconds.
    """
    target_words = duration_seconds * 3
    
    sys_prompt = f"""Bạn là một chuyên gia viết kịch bản video TikTok (Faceless) chốt sale và kể chuyện siêu cuốn hút.
Nhiệm vụ của bạn: Viết một kịch bản ngắn gọn, đi thẳng vào vấn đề về chủ đề được yêu cầu.

QUY TẮC CỐT LÕI:
1. Video này có thời lượng ĐÚNG {duration_seconds} giây. 
2. Trung bình người Việt đọc 3 từ mỗi giây, do đó kịch bản của bạn PHẢI dài khoảng {target_words} từ (chênh lệch tối đa 10 từ).
3. KHÔNG viết các chỉ dẫn hành động (ví dụ: [Nhạc nổi lên], [Cảnh quay], [Chuyển cảnh]).
4. CHỈ VIẾT DUY NHẤT lời thoại để cho AI Voice (TTS) đọc. Không có bất kỳ từ thừa nào.
5. Cấu trúc 3 phần: Hook (câu mở đầu gây sốc/tò mò) -> Body (Lợi ích/Giải pháp) -> CTA (Kêu gọi hành động: "Mua ngay ở giỏ hàng", "Xem ngay link dưới", v.v.).
6. Dùng ngôn ngữ tự nhiên, nói tiếng Việt chuẩn, có thể chèn các cảm thán nhẹ nhàng.
"""
    
    # Sử dụng model DeepSeek hoặc OpenAI đã cấu hình
    # Lấy base_url và api_key từ môi trường
    # Nếu không có DeepSeek, fallback về OpenAI mặc định
    openai_api_key = os.getenv("OPENAI_API_KEY")
    deepseek_api_key = os.getenv("DEEPSEEK_API_KEY")
    
    llm = None
    if deepseek_api_key:
        llm = ChatOpenAI(
            model="deepseek-v4-flash", 
            api_key=deepseek_api_key, 
            base_url="https://api.deepseek.com/v1",
            temperature=0.7
        )
    elif openai_api_key:
        llm = ChatOpenAI(
            model="gpt-4o-mini",
            api_key=openai_api_key,
            temperature=0.7
        )
    else:
        raise ValueError("Missing API Key for LLM (Need OPENAI_API_KEY or DEEPSEEK_API_KEY)")
        
    messages = [
        SystemMessage(content=sys_prompt),
        HumanMessage(content=f"Chủ đề: {topic}")
    ]
    
    print(f"[*] Generating script for topic '{topic}' (Target: {duration_seconds}s, ~{target_words} words)...")
    response = llm.invoke(messages)
    script = response.content.strip()
    
    print(f"[*] Script generated ({len(script.split())} words):\n{script}")
    return script

if __name__ == "__main__":
    from dotenv import load_dotenv
    # Load .env cho việc test local
    load_dotenv("../../.env")
    print(generate_tiktok_script("Review bình giữ nhiệt nắp gỗ khắc tên", 15))
