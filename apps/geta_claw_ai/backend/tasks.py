import os
import time
import duckdb
from celery_app import celery_app
from langchain_openai import ChatOpenAI
from langchain_core.messages import SystemMessage, HumanMessage
from facebook_agent import generate_social_post, generate_comment_reply, post_to_facebook, reply_to_facebook_comment
import json
import requests

def is_task_enabled(task_name: str) -> bool:
    config_path = "/app/task_config.json"
    if not os.path.exists(config_path):
        return True # Mặc định bật nếu file chưa tồn tại
    try:
        with open(config_path, "r", encoding="utf-8") as f:
            config = json.load(f)
        return config.get(task_name, True)
    except Exception as e:
        print(f"Error reading task config: {e}")
        return True

FACEBOOK_PAGES = [
    {"id": "1148071345056576", "name": "Nhà Phân Phối Ly Nhựa Tây Ninh", "env_token": "FB_PAGE_TOKEN_1148071345056576"},
    {"id": "1111674952036438", "name": "In Ly Tây Ninh", "env_token": "FB_PAGE_TOKEN_1111674952036438"},
    {"id": "1079779975224215", "name": "Geta Oasis - Xe nước lưu động Tây Ninh", "env_token": "FB_PAGE_TOKEN_1079779975224215"}
]

@celery_app.task
def auto_post_facebook():
    """Tự động đăng bài lên 3 Fanpage bằng AI."""
    print("=== STARTING AUTO POST FACEBOOK ===")
    if not is_task_enabled("auto_post_facebook"):
        print("Task 'auto_post_facebook' is disabled in config. Skipping.")
        return
        
    for page in FACEBOOK_PAGES:
        token = os.getenv(page["env_token"])
        if not token:
            print(f"Missing token for {page['name']}")
            continue
            
        print(f"Generating post for {page['name']}...")
        post_content = generate_social_post(page["name"])
        print(f"Posting to {page['name']}: {post_content}")
        
        res = post_to_facebook(page["id"], token, post_content)
        if "id" in res:
            print(f"Successfully posted to {page['name']}, Post ID: {res['id']}")
        else:
            print(f"Failed to post to {page['name']}")

@celery_app.task
def reply_facebook_comment_task(comment_id: str, comment_text: str, page_id: str):
    """Tự động trả lời bình luận bằng AI (chạy nền có delay để chống Spam)."""
    print(f"=== STARTING AUTO REPLY FOR COMMENT {comment_id} ===")
    
    page = next((p for p in FACEBOOK_PAGES if p["id"] == page_id), None)
    if not page:
        print(f"Page ID {page_id} not configured.")
        return
        
    token = os.getenv(page["env_token"])
    if not token:
        print(f"Missing token for {page['name']}")
        return
        
    print(f"Generating reply for comment on {page['name']}...")
    reply_content = generate_comment_reply(comment_text, page["name"])
    print(f"Replying: {reply_content}")
    
    res = reply_to_facebook_comment(comment_id, token, reply_content)
    if "id" in res:
        print(f"Successfully replied to comment {comment_id}, Reply ID: {res['id']}")
    else:
        print(f"Failed to reply to comment {comment_id}")

DB_URL = os.getenv("POSTGRES_URL", "postgresql://user:password@localhost:5432/automation_db")
url_sync = DB_URL.replace("postgresql://", "postgres://")

@celery_app.task
def analyze_and_adjust_ads():
    print("=== STARTING AD ANALYSIS LOOP ===")
    
    # 1. Kết nối DuckDB vào PostgreSQL
    con = duckdb.connect()
    con.execute("INSTALL postgres;")
    con.execute("LOAD postgres;")
    con.execute(f"ATTACH '{url_sync}' AS db (TYPE postgres);")
    
    # 2. Truy vấn ROAS bằng DuckDB
    query = """
    SELECT 
        a.campaign_id,
        a.platform,
        SUM(a.spend) as total_spend,
        SUM(o.total_amount) as total_revenue,
        CASE WHEN SUM(a.spend) > 0 THEN ROUND(SUM(o.total_amount) / SUM(a.spend), 2) ELSE 0 END as ROAS
    FROM db.ads_metrics a
    LEFT JOIN db.orders o ON a.campaign_id = o.campaign_id
    GROUP BY a.campaign_id, a.platform
    """
    results = con.execute(query).fetchall()
    columns = [desc[0] for desc in con.description]
    
    # Format kết quả thành chuỗi
    data_str = " | ".join(columns) + "\n"
    for row in results:
        data_str += " | ".join(str(v) for v in row) + "\n"
        
    print("DuckDB Analysis Results:")
    print(data_str)
    
    sys_prompt = """Bạn là một Media Buyer (Chuyên gia tối ưu quảng cáo) cấp cao.
Nhiệm vụ của bạn là đọc bảng số liệu ROAS (Return On Ad Spend) của các chiến dịch quảng cáo.
Nguyên tắc:
- Nếu ROAS > 3.0: Chiến dịch đang RẤT LÃI -> Tăng ngân sách (action: "increase_budget", value: 20%)
- Nếu 2.0 <= ROAS <= 3.0: Chiến dịch LÃI MỎNG -> Giữ nguyên (action: "keep_budget", value: 0%)
- Nếu ROAS < 2.0: Chiến dịch LỖ -> Giảm ngân sách hoặc tắt (action: "decrease_budget", value: -30%)

Bạn PHẢI trả về KẾT QUẢ ĐẦU RA DƯỚI DẠNG JSON MẢNG TƯƠNG ĐỐI NHƯ SAU (Không kèm markdown, không kèm giải thích, chỉ JSON thuần):
[
    {
        "campaign_id": "CMP_ID",
        "platform": "platform",
        "roas": 2.5,
        "action": "keep_budget",
        "value": "0%",
        "reason": "Lý do ngắn gọn"
    }
]
"""

    user_prompt = f"Bảng dữ liệu ROAS hiện tại:\n{data_str}"
    
    # 4. Gọi DeepSeek API
    api_key = os.getenv("DEEPSEEK_API_KEY")
    if not api_key:
        print("Lỗi: Thiếu DEEPSEEK_API_KEY")
        return
        
    print("Calling DeepSeek API for decision...")
    try:
        llm = ChatOpenAI(
            api_key=api_key, 
            base_url="https://api.deepseek.com/v1", 
            model="deepseek-v4-flash",
            temperature=0.1
        )
        
        response = invoke_gemini_with_retry([
            SystemMessage(content=sys_prompt),
            HumanMessage(content=user_prompt)
        ])
        
        # 5. Xử lý và in kết quả
        decision_json = response.content
        print("\n=== DEEPSEEK DECISION (JSON PAYLOAD) ===")
        print(decision_json)
        print("=========================================\n")
        
        # Ở đây có thể tích hợp code gọi API Facebook/Tiktok thực tế
        
    except Exception as e:
        print(f"Lỗi khi gọi AI: {e}")

import psutil
import subprocess
import requests

@celery_app.task
def monitor_system():
    print("=== STARTING SYSTEM MONITOR ===")
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    chat_id = os.getenv("TELEGRAM_CHAT_ID")
    
    if not token or not chat_id:
        print("Thiếu cấu hình Telegram")
        return
        
    alerts = []
    
    # 1. Kiểm tra RAM
    mem = psutil.virtual_memory()
    free_ram_gb = mem.available / (1024**3)
    if free_ram_gb < 1.0:
        alerts.append(f"⚠️ Cảnh báo RAM: Chỉ còn {free_ram_gb:.2f}GB trống!")
        
    # 2. Kiểm tra Nhiệt độ GPU (nếu có)
    try:
        smi_out = subprocess.check_output(
            ["nvidia-smi", "--query-gpu=temperature.gpu", "--format=csv,noheader"], 
            stderr=subprocess.STDOUT
        ).decode("utf-8").strip()
        
        temps = [int(t) for t in smi_out.split('\n') if t.isdigit()]
        for idx, temp in enumerate(temps):
            if temp > 85:
                alerts.append(f"🔥 Cảnh báo GPU {idx}: Nhiệt độ quá cao {temp}°C!")
    except Exception as e:
        print("Không thể đo nhiệt độ GPU (Bỏ qua):", e)
        
    # 3. Gửi cảnh báo
    if alerts:
        msg = "🚨 **CẢNH BÁO HỆ THỐNG** 🚨\n\n" + "\n".join(alerts)
        url = f"https://api.telegram.org/bot{token}/sendMessage"
        try:
            requests.post(url, json={"chat_id": chat_id, "text": msg, "parse_mode": "Markdown"})
            print("Đã gửi cảnh báo Telegram!")
        except Exception as e:
            print("Lỗi khi gửi Telegram:", e)
    else:
        print("Hệ thống hoạt động bình thường.")

import sys
import subprocess

@celery_app.task
def run_group_search_join_task(keyword: str = None, urls: list[str] = None):
    """Chạy ngầm script tự động tìm kiếm và tham gia nhóm."""
    log_file_path = "/app/scripts/joined_log.txt"
    with open(log_file_path, "a", encoding="utf-8") as lf:
        lf.write(f"\n[{time.strftime('%Y-%m-%d %H:%M:%S')}] === STARTING GROUP SEARCH & JOIN TASK ===\n")
    try:
        script_path = "/app/scripts/group_search_join.py"
        args = [sys.executable, script_path, keyword or ""]
        if urls:
            args.append(json.dumps(urls))
        result = subprocess.run(
            args,
            capture_output=True,
            text=True,
            check=True
        )
        with open(log_file_path, "a", encoding="utf-8") as lf:
            lf.write(result.stdout + "\n")
            lf.write(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] === FINISHED GROUP SEARCH & JOIN TASK ===\n")
    except subprocess.CalledProcessError as e:
        with open(log_file_path, "a", encoding="utf-8") as lf:
            lf.write(f"❌ Error running search and join task: {e}\n")
            lf.write("Stdout: " + (e.stdout or "") + "\n")
            lf.write("Stderr: " + (e.stderr or "") + "\n")

@celery_app.task
def run_group_auto_poster_task():
    """Chạy ngầm script tự động đăng bài vào nhóm."""
    print("=== STARTING GROUP AUTO POSTER TASK ===")
    try:
        script_path = "/app/scripts/group_auto_poster.py"
        result = subprocess.run(
            [sys.executable, script_path],
            capture_output=True,
            text=True,
            check=True
        )
        print("Stdout:", result.stdout)
        print("Stderr:", result.stderr)
        print("=== FINISHED GROUP AUTO POSTER TASK ===")
    except subprocess.CalledProcessError as e:
        print(f"Error running group auto poster task: {e}")
        print("Stdout:", e.stdout)
        print("Stderr:", e.stderr)

@celery_app.task
def run_group_crawler_task(keyword: str):
    """Chạy ngầm script tự động cào/thu thập nhóm."""
    log_file_path = "/app/scripts/joined_log.txt"
    with open(log_file_path, "a", encoding="utf-8") as lf:
        lf.write(f"\n[{time.strftime('%Y-%m-%d %H:%M:%S')}] === STARTING GROUP CRAWLER TASK FOR '{keyword}' ===\n")
    try:
        script_path = "/app/scripts/group_crawler.py"
        result = subprocess.run(
            [sys.executable, script_path, keyword],
            capture_output=True,
            text=True,
            check=True
        )
        with open(log_file_path, "a", encoding="utf-8") as lf:
            lf.write(result.stdout + "\n")
            lf.write(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] === FINISHED GROUP CRAWLER TASK ===\n")
    except subprocess.CalledProcessError as e:
        with open(log_file_path, "a", encoding="utf-8") as lf:
            lf.write(f"❌ Error running group crawler task: {e}\n")
            lf.write("Stdout: " + (e.stdout or "") + "\n")
            lf.write("Stderr: " + (e.stderr or "") + "\n")

import base64
import requests
import json
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.messages import HumanMessage, SystemMessage


def invoke_gemini_with_retry(messages, temperature=0.7):
    from langchain_google_genai import ChatGoogleGenerativeAI
    import os, random, time
    keys = os.environ.get("GEMINI_API_KEYS", "")
    if not keys: raise Exception("Không tìm thấy GEMINI_API_KEYS")
    key_list = [k.strip() for k in keys.split(",") if k.strip()]
    random.shuffle(key_list)
    last_error = None
    for key in key_list:
        try:
            llm = ChatGoogleGenerativeAI(model="gemini-2.5-flash", temperature=temperature, google_api_key=key)
            return llm.invoke(messages)
        except Exception as e:
            last_error = e
            if "429" in str(e) or "RESOURCE_EXHAUSTED" in str(e) or "quota" in str(e).lower():
                print(f"Key {key[:10]}... bị limit, thử key khác...")
                time.sleep(1)
                continue
            raise e
    raise Exception(f"Tất cả API keys đều bị lỗi (Limit): {last_error}")

def get_gemini_key() -> str:
    keys_str = os.getenv("GEMINI_API_KEYS", "")
    keys = [k.strip() for k in keys_str.split(",") if k.strip()]
    return keys[0] if keys else ""

import urllib.parse
def generate_image_via_gemini(prompt: str, output_path: str, aspect_ratio: str = "1:1") -> bool:
    """Sử dụng API miễn phí Pollinations.ai (hoặc AI tạo ảnh khác) thay cho Imagen 3 (do API Imagen bị thay đổi/khóa)."""
    try:
        width, height = 1024, 1024
        if aspect_ratio == "16:9":
            width, height = 1024, 576
        elif aspect_ratio == "4:3":
            width, height = 1024, 768
        elif aspect_ratio == "3:4":
            width, height = 768, 1024
            
        encoded_prompt = urllib.parse.quote(prompt)
        url = f"https://image.pollinations.ai/prompt/{encoded_prompt}?width={width}&height={height}&nologo=true"
        
        print(f"Requesting image from: {url}")
        res = requests.get(url, timeout=30)
        res.raise_for_status()
        
        with open(output_path, "wb") as f:
            f.write(res.content)
            
        print(f"✅ Đã tạo file ảnh thành công: {output_path}")
        return True
    except Exception as e:
        print(f"Lỗi khi vẽ ảnh bằng AI: {e}")
        raise Exception(f"Lỗi vẽ ảnh AI: {str(e)}")
        return False

@celery_app.task
def generate_campaign_content_task(keyword: str, vibe: str = "professional", aspect_ratio: str = "1:1"):
    """Tạo bài viết và vẽ hình ảnh bằng AI dựa trên từ khóa, lưu vào thư viện."""
    print(f"=== STARTING AI CAMPAIGN GENERATOR FOR '{keyword}' WITH VIBE '{vibe}' AND ASPECT RATIO '{aspect_ratio}' ===")
    api_key = get_gemini_key()
    if not api_key:
        print("Lỗi: Không tìm thấy GEMINI_API_KEYS")
        return
        
    # Tạo thư mục lưu trữ nếu chưa có
    content_dir = "/app/scripts/content"
    images_dir = "/app/scripts/images"
    os.makedirs(content_dir, exist_ok=True)
    os.makedirs(images_dir, exist_ok=True)
    
    timestamp = int(time.time())
    safe_keyword = "".join(c for c in keyword if c.isalnum() or c in (' ', '_')).rstrip().replace(' ', '_')
    if len(safe_keyword) > 30:
        safe_keyword = safe_keyword[:30].rstrip('_')
    
    # 1. Sinh bài viết
    try:
        
        # Ánh xạ phong cách văn phong
        vibe_instruction = "Viết bằng giọng văn chuyên nghiệp, lịch sự, tập trung vào giá trị."
        if vibe == "humorous":
            vibe_instruction = "Viết bằng giọng văn hài hước, dí dỏm, tạo tiếng cười vui vẻ, thân thiện."
        elif vibe == "sales":
            vibe_instruction = "Viết bằng giọng văn thuyết phục, tập trung bán hàng, nêu bật ưu đãi và có lời kêu gọi hành động (CTA) cực mạnh."
        elif vibe == "recruitment":
            vibe_instruction = "Viết bằng giọng văn trang trọng, rõ ràng về các yêu cầu, quyền lợi tuyển dụng và cách nộp hồ sơ."
        elif vibe == "casual":
            vibe_instruction = "Viết bằng giọng văn gần gũi, đời thường, chia sẻ thân mật như một người bạn."

        sys_prompt = (
            "Bạn là chuyên gia Content Marketing. Hãy viết một bài đăng Facebook ngắn gọn (dưới 150 chữ), "
            "cực kỳ thu hút về chủ đề được yêu cầu.\n"
            f"Phong cách/Vibe viết bài: {vibe_instruction}\n"
            "Yêu cầu bắt buộc về cấu trúc bài viết:\n"
            "1. Bài viết bắt buộc phải chia làm 3 phần rõ ràng, cách nhau bởi các dòng trống:\n"
            "   - HEADLINE: Một dòng tiêu đề ngắn gọn, viết HOA hoàn toàn để gây ấn tượng mạnh.\n"
            "   - BODY: Thân bài chứa thông tin chi tiết chính về từ khóa (ví dụ: mô tả công việc, quyền lợi, yêu cầu).\n"
            "   - FOOTER: Phần chân bài chứa lời kêu gọi hành động (CTA), thông tin liên hệ (Địa chỉ/SĐT) và các hashtag liên quan.\n"
            "2. Tuyệt đối không viết các câu chào hỏi mở đầu rườm rà ở trên cùng (ví dụ: không ghi 'Chào mọi người...', 'Dưới đây là tin tuyển dụng...'). Hãy bắt đầu bài đăng ngay bằng dòng HEADLINE.\n"
            "3. Chỉ xuất ra nội dung bài đăng chính, không thêm bất cứ thông tin thừa thãi nào.\n"
            "4. Tuyệt đối viết bằng văn bản thuần túy (plain text) 100%, không sử dụng bất kỳ chữ in đậm (bold), chữ in nghiêng (italic) hay định dạng Markdown nào (không dùng dấu sao **, không dùng tiêu đề #, không dùng danh sách hoa thị).\n"
            "5. Sử dụng cực kỳ ít icon/emoji (chỉ sử dụng tối đa 1-2 cái cho toàn bộ bài đăng).\n"
            "6. GIỮ NGUYÊN THÔNG TIN THỰC TẾ: Nếu trong mô tả/từ khóa của người dùng có chứa thông tin liên hệ thực tế (như số điện thoại, địa chỉ, email, tên thương hiệu/công ty), bạn BẮT BUỘC phải giữ nguyên và điền các thông tin thực tế đó vào bài viết (đặc biệt là phần FOOTER). Tuyệt đối không tự ý ẩn đi hay thay thế chúng bằng các ký hiệu giữ chỗ mẫu như 09xx.xxx.xxx, [Địa chỉ], [Tên Công ty]."
        )
        response = invoke_gemini_with_retry([SystemMessage(content=sys_prompt), HumanMessage(content=f"Chủ đề/Từ khóa: '{keyword}'")])
        post_text = response.content
        
        # Lưu file text
        text_filename = f"{timestamp}_{safe_keyword}.txt"
        text_path = os.path.join(content_dir, text_filename)
        with open(text_path, "w", encoding="utf-8") as f:
            f.write(post_text)
        print(f"✅ Đã tạo file chữ: {text_path}")
    except Exception as e:
        print(f"Lỗi tạo bài viết: {e}")
        return

    # 2. Sinh prompt vẽ ảnh và vẽ ảnh
    try:
        # Nhờ AI viết một prompt tiếng Anh ngắn để vẽ ảnh
        image_prompt_msg = f"Dựa vào bài đăng sau: '{post_text}'. Hãy viết một câu prompt tiếng Anh (dưới 50 từ) để vẽ một bức ảnh chất lượng cao minh họa cho bài đăng này. BẮT BUỘC thêm yêu cầu KHÔNG chứa chữ viết (no text, no letters). Chỉ trả về câu prompt tiếng Anh đó, không thêm giải thích."
        prompt_res = invoke_gemini_with_retry([HumanMessage(content=image_prompt_msg)])
        draw_prompt = prompt_res.content.strip()
        
        # Bổ sung một số style đẹp
        draw_prompt += ", professional graphic design, modern, 4k"
        print(f"Prompt vẽ ảnh: {draw_prompt}")
        
        # Gọi vẽ ảnh
        image_filename = f"{timestamp}_{safe_keyword}.jpg"
        image_path = os.path.join(images_dir, image_filename)
        success = generate_image_via_gemini(draw_prompt, image_path, aspect_ratio=aspect_ratio)
        
        # Ghi nhật ký vào log
        log_file_path = "/app/scripts/joined_log.txt"
        with open(log_file_path, "a", encoding="utf-8") as lf:
            lf.write(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] [AI Content Gen] Đã tạo thành công bài viết '{text_filename}' và hình ảnh '{image_filename}' cho từ khóa '{keyword}'\n")
            
    except Exception as e:
        print(f"Lỗi tạo ảnh: {e}")

@celery_app.task
def run_custom_campaign_task(config: dict):
    """Chạy chiến dịch đăng bài tùy chọn dựa vào cấu hình gửi từ UI."""
    print("=== STARTING CUSTOM FB CAMPAIGN TASK ===")
    
    script_dir = "/app/scripts"
    config_file_path = os.path.join(script_dir, "campaign_config.json")
    log_file_path = os.path.join(script_dir, "joined_log.txt")
    
    # 0. Thực hiện sinh bài viết/ảnh tự động bằng AI nếu được cấu hình chọn nguồn AI
    content_source = config.get("content_source", "library")
    image_source = config.get("image_source", "library")
    
    api_key = get_gemini_key()
    timestamp = int(time.time())
    
    # Sinh content bằng AI nếu được chỉ định
    if content_source == "ai":
        keyword = config.get("content_keyword", "")
        vibe = config.get("content_vibe", "professional")
        if keyword and api_key:
            print(f"Generating content on-the-fly for custom campaign using keyword '{keyword}'...")
            try:
                os.makedirs("/app/scripts/content", exist_ok=True)
                safe_keyword = "".join(c for c in keyword if c.isalnum() or c in (' ', '_')).rstrip().replace(' ', '_')
                if len(safe_keyword) > 30:
                    safe_keyword = safe_keyword[:30].rstrip('_')
                
                vibe_instruction = "Viết bằng giọng văn chuyên nghiệp, lịch sự, tập trung vào giá trị."
                if vibe == "humorous":
                    vibe_instruction = "Viết bằng giọng văn hài hước, dí dỏm, tạo tiếng cười vui vẻ, thân thiện."
                elif vibe == "sales":
                    vibe_instruction = "Viết bằng giọng văn thuyết phục, tập trung bán hàng, nêu bật ưu đãi và có lời kêu gọi hành động (CTA) cực mạnh."
                elif vibe == "recruitment":
                    vibe_instruction = "Viết bằng giọng văn trang trọng, rõ ràng về các yêu cầu, quyền lợi tuyển dụng và cách nộp hồ sơ."
                elif vibe == "casual":
                    vibe_instruction = "Viết bằng giọng văn gần gũi, đời thường, chia sẻ thân mật như một người bạn."

                sys_prompt = (
                    "Bạn là chuyên gia Content Marketing. Hãy viết một bài đăng Facebook ngắn gọn (dưới 150 chữ), "
                    "cực kỳ thu hút về chủ đề được yêu cầu.\n"
                    f"Phong cách/Vibe viết bài: {vibe_instruction}\n"
                    "Yêu cầu bắt buộc về cấu trúc bài viết:\n"
                    "1. Bài viết bắt buộc phải chia làm 3 phần rõ ràng, cách nhau bởi các dòng trống:\n"
                    "   - HEADLINE: Một dòng tiêu đề ngắn gọn, viết HOA hoàn toàn để gây ấn tượng mạnh.\n"
                    "   - BODY: Thân bài chứa thông tin chi tiết chính về từ khóa (ví dụ: mô tả công việc, quyền lợi, yêu cầu).\n"
                    "   - FOOTER: Phần chân bài chứa lời kêu gọi hành động (CTA), thông tin liên hệ (Địa chỉ/SĐT) và các hashtag liên quan.\n"
                    "2. Tuyệt đối không viết các câu chào hỏi mở đầu rườm rà ở trên cùng (ví dụ: không ghi 'Chào mọi người...', 'Dưới đây là tin tuyển dụng...'). Hãy bắt đầu bài đăng ngay bằng dòng HEADLINE.\n"
                    "3. Chỉ xuất ra nội dung bài đăng chính, không thêm bất cứ thông tin thừa thãi nào.\n"
                    "4. Tuyệt đối viết bằng văn bản thuần túy (plain text) 100%, không sử dụng bất kỳ chữ in đậm (bold), chữ in nghiêng (italic) hay định dạng Markdown nào (không dùng dấu sao **, không dùng tiêu đề #, không dùng danh sách hoa thị).\n"
                    "5. Sử dụng cực kỳ ít icon/emoji (chỉ sử dụng tối đa 1-2 cái cho toàn bộ bài đăng).\n"
                    "6. GIỮ NGUYÊN THÔNG TIN THỰC TẾ: Nếu trong mô tả/từ khóa của người dùng có chứa thông tin liên hệ thực tế (như số điện thoại, địa chỉ, email, tên thương hiệu/công ty), bạn BẮT BUỘC phải giữ nguyên và điền các thông tin thực tế đó vào bài viết (đặc biệt là phần FOOTER). Tuyệt đối không tự ý ẩn đi hay thay thế chúng bằng các ký hiệu giữ chỗ mẫu như 09xx.xxx.xxx, [Địa chỉ], [Tên Công ty]."
                )
                response = invoke_gemini_with_retry([SystemMessage(content=sys_prompt), HumanMessage(content=f"Chủ đề/Từ khóa: '{keyword}'")])
                post_text = response.content
                
                text_filename = f"ai_gen_{timestamp}_{safe_keyword}.txt"
                text_path = os.path.join("/app/scripts/content", text_filename)
                with open(text_path, "w", encoding="utf-8") as f:
                    f.write(post_text)
                
                config["content_file"] = text_filename
                print(f"✅ Generated AI text content on-the-fly: {text_filename}")
            except Exception as e:
                print(f"❌ Failed to generate AI content on-the-fly: {e}")

    # Sinh ảnh bằng AI nếu được chỉ định
    if image_source == "ai":
        image_prompt = config.get("image_prompt", "")
        # Nếu rỗng, cố gắng dùng chính bài viết AI vừa tạo để làm prompt
        if not image_prompt and content_source == "ai" and "content_file" in config:
            try:
                text_path = os.path.join("/app/scripts/content", config["content_file"])
                with open(text_path, "r", encoding="utf-8") as f:
                    post_text = f.read()
                
                llm = ChatGoogleGenerativeAI(
                    model="gemini-2.5-flash",
                    google_api_key=api_key
                )
                image_prompt_msg = f"Dựa vào bài đăng sau: '{post_text}'. Hãy viết một câu prompt tiếng Anh (dưới 50 từ) để vẽ một bức ảnh chất lượng cao minh họa cho bài đăng này. BẮT BUỘC thêm yêu cầu KHÔNG chứa chữ viết (no text, no letters). Chỉ trả về câu prompt tiếng Anh đó, không thêm giải thích."
                prompt_res = invoke_gemini_with_retry([HumanMessage(content=image_prompt_msg)])
                image_prompt = prompt_res.content.strip() + ", professional graphic design, modern, 4k, strictly NO TEXT, no letters, no words, no typography, clean background"
            except Exception as pe:
                print(f"⚠️ Lỗi sinh prompt vẽ ảnh: {pe}")
                
        if image_prompt and api_key:
            print(f"Generating image on-the-fly for custom campaign using prompt '{image_prompt}'...")
            try:
                os.makedirs("/app/scripts/images", exist_ok=True)
                image_filename = f"ai_gen_{timestamp}.jpg"
                image_path = os.path.join("/app/scripts/images", image_filename)
                
                if generate_image_via_gemini(image_prompt, image_path):
                    config["image_file"] = image_filename
                    print(f"✅ Generated AI image content on-the-fly: {image_filename}")
            except Exception as e:
                print(f"❌ Failed to generate AI image on-the-fly: {e}")
                
    try:
        # 1. Ghi file cấu hình tạm
        with open(config_file_path, "w", encoding="utf-8") as f:
            json.dump(config, f, ensure_ascii=False, indent=2)
        print(f"✅ Đã ghi cấu hình chiến dịch tạm thời vào: {config_file_path}")
        
        # Ghi log bắt đầu chiến dịch
        with open(log_file_path, "a", encoding="utf-8") as lf:
            lf.write(f"\n[{time.strftime('%Y-%m-%d %H:%M:%S')}] === KHỞI ĐỘNG CHIẾN DỊCH ĐĂNG BÀI ===\n")
            lf.write(f"Tác nhân: {config.get('profile_type', 'user').upper()} {config.get('page_name', '')}\n")
            lf.write(f"Nội dung: {config.get('content_file', 'mặc định')}\n")
            lf.write(f"Ảnh: {config.get('image_file', 'không có')}\n")
            lf.write(f"Số lượng nhóm đích: {len(config.get('groups', []))} nhóm\n")
        
        # 2. Chạy group_auto_poster.py
        script_path = os.path.join(script_dir, "group_auto_poster.py")
        result = subprocess.run(
            [sys.executable, script_path],
            capture_output=True,
            text=True,
            check=True
        )
        
        # Ghi log kết quả
        with open(log_file_path, "a", encoding="utf-8") as lf:
            lf.write(result.stdout)
            lf.write(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] === CHIẾN DỊCH HOÀN TẤT THÀNH CÔNG ===\n")
            
        print("Stdout:", result.stdout)
        print("Stderr:", result.stderr)
        
    except subprocess.CalledProcessError as e:
        print(f"Error running campaign: {e}")
        # Ghi log lỗi
        with open(log_file_path, "a", encoding="utf-8") as lf:
            lf.write(f"❌ CHIẾN DỊCH THẤT BẠI: Lỗi khi chạy kịch bản tự động.\n")
            lf.write(e.stderr + "\n")
        print("Stdout:", e.stdout)
        print("Stderr:", e.stderr)
    except Exception as ex:
        print(f"Error starting campaign: {ex}")
        with open(log_file_path, "a", encoding="utf-8") as lf:
            lf.write(f"❌ CHIẾN DỊCH THẤT BẠI: {str(ex)}\n")

@celery_app.task
def run_group_crawler_task(keyword: str):
    """Chạy ngầm script tự động cào/thu thập nhóm."""
    log_file_path = "/app/scripts/joined_log.txt"
    import time
    with open(log_file_path, "a", encoding="utf-8") as lf:
        lf.write(f"\n[{time.strftime('%Y-%m-%d %H:%M:%S')}] === KHỞI ĐỘNG CÀO THU THẬP NHÓM ===\n")
        lf.write(f"Từ khóa tìm kiếm: {keyword}\n")
    try:
        script_path = "/app/scripts/group_crawler.py"
        process = subprocess.Popen(
            [sys.executable, "-u", script_path, keyword],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
            encoding="utf-8"
        )
        for line in process.stdout:
            print(line, end="")
            with open(log_file_path, "a", encoding="utf-8") as lf:
                lf.write(line)
        process.wait()
        if process.returncode == 0:
            with open(log_file_path, "a", encoding="utf-8") as lf:
                lf.write(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] === CÀO NHÓM HOÀN TẤT THÀNH CÔNG ===\n")
        else:
            with open(log_file_path, "a", encoding="utf-8") as lf:
                lf.write(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] ❌ CÀO NHÓM THẤT BẠI với mã lỗi {process.returncode}\n")
    except Exception as e:
        print(f"Error running group crawler task: {e}")
        with open(log_file_path, "a", encoding="utf-8") as lf:
            lf.write(f"❌ LỖI HỆ THỐNG: {str(e)}\n")

@celery_app.task
def run_market_research_task(query: str, sources: list = None, limits: dict = None):
    """Chạy ngầm script tự động nghiên cứu thị trường."""
    log_file_path = "/app/scripts/joined_log.txt"
    import time
    with open(log_file_path, "a", encoding="utf-8") as lf:
        lf.write(f"\n[{time.strftime('%Y-%m-%d %H:%M:%S')}] === KHỞI ĐỘNG NGHIÊN CỨU THỊ TRƯỜNG ===\n")
        lf.write(f"Từ khóa: {query}\n")
        lf.write(f"Nguồn cần cào: {', '.join(sources) if sources else 'không có'}\n")
    try:
        import json
        script_path = "/app/scripts/market_research.py"
        cmd = [sys.executable, "-u", script_path, "--query", query]
        if sources:
            cmd.extend(["--sources", ",".join(sources)])
        if limits:
            cmd.extend(["--limits", json.dumps(limits)])
        
        process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
            encoding="utf-8"
        )
        for line in process.stdout:
            print(line, end="")
            with open(log_file_path, "a", encoding="utf-8") as lf:
                lf.write(line)
        process.wait()
        if process.returncode == 0:
            with open(log_file_path, "a", encoding="utf-8") as lf:
                lf.write(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] === NGHIÊN CỨU HOÀN TẤT THÀNH CÔNG ===\n")
        else:
            with open(log_file_path, "a", encoding="utf-8") as lf:
                lf.write(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] ❌ NGHIÊN CỨU THẤT BẠI với mã lỗi {process.returncode}\n")
    except Exception as e:
        print(f"Error running market research task: {e}")
        with open(log_file_path, "a", encoding="utf-8") as lf:
            lf.write(f"❌ LỖI HỆ THỐNG: {str(e)}\n")

@celery_app.task
def export_to_zalo_crm_task(selected_links: list = None):
    """Chạy ngầm script đồng bộ dữ liệu nghiên cứu qua Zalo CRM."""
    print("=== STARTING EXPORT TO ZALO CRM TASK ===")
    try:
        script_path = "/app/scripts/export_to_zalo_crm.py"
        cmd = [sys.executable, script_path]
        if selected_links:
            cmd.extend(["--links", ",".join(selected_links)])
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            check=True
        )
        print("Stdout:", result.stdout)
        print("Stderr:", result.stderr)
        print("=== FINISHED EXPORT TO ZALO CRM TASK ===")
    except subprocess.CalledProcessError as e:
        print(f"Error running export to Zalo CRM task: {e}")
        print("Stdout:", e.stdout)
        print("Stderr:", e.stderr)


@celery_app.task
def generate_content_only_task(keyword: str, vibe: str = "professional"):
    """Tạo bài viết bằng AI dựa trên từ khóa, lưu vào thư viện."""
    print(f"=== STARTING AI CONTENT GENERATOR ONLY FOR '{keyword}' WITH VIBE '{vibe}' ===")
    api_key = get_gemini_key()
    if not api_key:
        print("Lỗi: Không tìm thấy GEMINI_API_KEYS")
        return
        
    content_dir = "/app/scripts/content"
    os.makedirs(content_dir, exist_ok=True)
    
    timestamp = int(time.time())
    safe_keyword = "".join(c for c in keyword if c.isalnum() or c in (' ', '_')).rstrip().replace(' ', '_')
    if len(safe_keyword) > 30:
        safe_keyword = safe_keyword[:30].rstrip('_')
    
    try:
        
        vibe_instruction = "Viết bằng giọng văn chuyên nghiệp, lịch sự, tập trung vào giá trị."
        if vibe == "humorous":
            vibe_instruction = "Viết bằng giọng văn hài hước, dí dỏm, tạo tiếng cười vui vẻ, thân thiện."
        elif vibe == "sales":
            vibe_instruction = "Viết bằng giọng văn thuyết phục, tập trung bán hàng, nêu bật ưu đãi và có lời kêu gọi hành động (CTA) cực mạnh."
        elif vibe == "recruitment":
            vibe_instruction = "Viết bằng giọng văn trang trọng, rõ ràng về các yêu cầu, quyền lợi tuyển dụng và cách nộp hồ sơ."
        elif vibe == "casual":
            vibe_instruction = "Viết bằng giọng văn gần gũi, đời thường, chia sẻ thân mật như một người bạn."

        sys_prompt = (
            "Bạn là chuyên gia Content Marketing. Hãy viết một bài đăng Facebook ngắn gọn (dưới 150 chữ), "
            "cực kỳ thu hút về chủ đề được yêu cầu.\n"
            f"Phong cách/Vibe viết bài: {vibe_instruction}\n"
            "Yêu cầu bắt buộc về cấu trúc bài viết:\n"
            "1. Bài viết bắt buộc phải chia làm 3 phần rõ ràng, cách nhau bởi các dòng trống:\n"
            "   - HEADLINE: Một dòng tiêu đề ngắn gọn, viết HOA hoàn toàn để gây ấn tượng mạnh.\n"
            "   - BODY: Thân bài chứa thông tin chi tiết chính về từ khóa (ví dụ: mô tả công việc, quyền lợi, yêu cầu).\n"
            "   - FOOTER: Phần chân bài chứa lời kêu gọi hành động (CTA), thông tin liên hệ (Địa chỉ/SĐT) và các hashtag liên quan.\n"
            "2. Tuyệt đối không viết các câu chào hỏi mở đầu rườm rà ở trên cùng (ví dụ: không ghi 'Chào mọi người...', 'Dưới đây là tin tuyển dụng...'). Hãy bắt đầu bài đăng ngay bằng dòng HEADLINE.\n"
            "3. Chỉ xuất ra nội dung bài đăng chính, không thêm bất cứ thông tin thừa thãi nào.\n"
            "4. Tuyệt đối viết bằng văn bản thuần túy (plain text) 100%, không sử dụng bất kỳ chữ in đậm (bold), chữ in nghiêng (italic) hay định dạng Markdown nào (không dùng dấu sao **, không dùng tiêu đề #, không dùng danh sách hoa thị).\n"
            "5. Sử dụng cực kỳ ít icon/emoji (chỉ sử dụng tối đa 1-2 cái cho toàn bộ bài đăng).\n"
            "6. GIỮ NGUYÊN THÔNG TIN THỰC TẾ: Nếu trong mô tả/từ khóa của người dùng có chứa thông tin liên hệ thực tế (như số điện thoại, địa chỉ, email, tên thương hiệu/công ty), bạn BẮT BUỘC phải giữ nguyên và điền các thông tin thực tế đó vào bài viết (đặc biệt là phần FOOTER). Tuyệt đối không tự ý ẩn đi hay thay thế chúng bằng các ký hiệu giữ chỗ mẫu như 09xx.xxx.xxx, [Địa chỉ], [Tên Công ty]."
        )
        response = invoke_gemini_with_retry([SystemMessage(content=sys_prompt), HumanMessage(content=f"Chủ đề/Từ khóa: '{keyword}'")])
        post_text = response.content
        
        text_filename = f"{timestamp}_{safe_keyword}.txt"
        text_path = os.path.join(content_dir, text_filename)
        with open(text_path, "w", encoding="utf-8") as f:
            f.write(post_text)
        print(f"✅ Đã tạo file chữ: {text_path}")
        
    except Exception as e:
        print(f"Lỗi khi gọi Gemini: {e}")
        raise Exception(f"Lỗi vẽ ảnh: {e}")

@celery_app.task
def generate_image_only_task(keyword: str, aspect_ratio: str = "1:1"):
    """Tạo hình ảnh bằng AI (Imagen) dựa trên từ khóa, lưu vào thư viện."""
    print(f"=== STARTING AI IMAGE GENERATOR ONLY FOR '{keyword}' WITH ASPECT RATIO '{aspect_ratio}' ===")
    api_key = get_gemini_key()
    if not api_key:
        print("Lỗi: Không tìm thấy GEMINI_API_KEYS")
        return
        
    images_dir = "/app/scripts/images"
    os.makedirs(images_dir, exist_ok=True)
    
    timestamp = int(time.time())
    safe_keyword = "".join(c for c in keyword if c.isalnum() or c in (' ', '_')).rstrip().replace(' ', '_')
    if len(safe_keyword) > 30:
        safe_keyword = safe_keyword[:30].rstrip('_')
    
    try:
        # Use Gemini to generate an image prompt
        img_prompt_req = f"""Tôi cần một prompt tiếng Anh để đưa vào AI vẽ ảnh.
Dưới đây là yêu cầu hoặc chủ đề của người dùng:
"{keyword}"

Quy tắc:
1. Nếu yêu cầu trên ĐÃ LÀ một prompt mô tả ảnh bằng tiếng Anh chi tiết, hãy GIỮ NGUYÊN nội dung cốt lõi, chỉ sửa lỗi ngữ pháp nếu có.
2. Nếu yêu cầu trên là tiếng Việt hoặc là một cụm từ ngắn, hãy sáng tạo một prompt tiếng Anh thật chi tiết (bối cảnh, ánh sáng, màu sắc) minh họa cho chủ đề đó.
3. TUYỆT ĐỐI thêm vào cuối prompt cụm từ: ", strictly NO TEXT, no letters, no words, no watermarks".
4. CHỈ xuất prompt tiếng Anh. TUYỆT ĐỐI KHÔNG giải thích, không có lời mở đầu."""
        response = invoke_gemini_with_retry([HumanMessage(content=img_prompt_req)])
        imagen_prompt = response.content.strip()
        print(f"Imagen Prompt: {imagen_prompt}")
        
        img_filename = f"{timestamp}_{safe_keyword}.jpg"
        img_path = os.path.join(images_dir, img_filename)
        
        generate_image_via_gemini(imagen_prompt, img_path, aspect_ratio)
        
    except Exception as e:
        print(f"Lỗi khi gọi Gemini: {e}")
        raise Exception(f"Lỗi vẽ ảnh: {e}")

@celery_app.task
def generate_blog_task():
    """Lấy các bài viết PENDING, sinh markdown, gửi Telegram, và gọi UI chọn Site."""
    print("=== STARTING GENERATE BLOG TASK ===")
    
    import sys
    import os
    blog_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '../blog_tool'))
    if blog_dir not in sys.path:
        sys.path.append(blog_dir)
        
    try:
        from database.session import init_db
        from database.models import ArticleStatus
        from services.article_repository import ArticleRepository
        from llm_engine.agent import SEOAgent
        from services.orchestrator import ArticleOrchestrator
        from backend.workflow_engine import start_site_selection_workflow

        init_db()
        options = ArticleRepository.get_processable_options()
        if not options:
            print("No pending articles found.")
            return

        # Lấy bài viết mới nhất đang chờ
        article_ids = sorted(list(options.values()))
        article_id = article_ids[-1]
        print(f"Processing article ID: {article_id}")
        
        article = ArticleRepository.get_article_by_id(article_id)
        if not article:
            return

        agent = SEOAgent()
        # Orchestrator cần wp_publisher dummy nếu không nó có thể crash
        from integrations.wordpress import WordPressPublisher
        dummy_pub = WordPressPublisher("https://dummy.com", "user", "pass")
        orchestrator = ArticleOrchestrator(agent=agent, wp_publisher=dummy_pub)

        # 1. Prepare image processing callback
        import json
        source_images_json = getattr(article, "source_images", "[]")
        target_site = getattr(article, "target_site", None)
        try:
            source_images = json.loads(source_images_json) if source_images_json else []
        except:
            source_images = []

        def process_images_callback(ai_output, article_ref):
            if source_images:
                from services.content_service import ContentService
                if all(item.startswith("http") for item in source_images):
                    ai_output["content_markdown"] = ContentService.inject_wp_media_urls_into_markdown(
                        ai_output.get("content_markdown", ""),
                        source_images,
                        len(source_images)
                    )
                else:
                    ai_output["content_markdown"] = ContentService.inject_images_into_markdown(
                        ai_output.get("content_markdown", ""),
                        source_images,
                        len(source_images)
                    )
            return ai_output

        # 2. Generate (Chỉ chạy 1 lần)
        is_gen_success, gen_msg = orchestrator.generate_single_article(
            article_id=article_id,
            language_label="Tiếng Việt",
            language_prompt="Vietnamese",
            site_name=target_site,
            ai_output_processor_callback=process_images_callback
        )
        if not is_gen_success:
            print(f"Generate failed: {gen_msg}")
            return
            
        print("Generate success!")
        
        # Đổi status thành AWAITING_SITE
        ArticleRepository.update_processing_state(article_id, ArticleStatus.AWAITING_SITE, "Chờ chọn Website")
        article = ArticleRepository.get_article_by_id(article_id) # reload
        
        # Gửi Telegram file MD
        import os
        from dotenv import load_dotenv
        blog_env_path = os.path.abspath(os.path.join(os.path.dirname(__file__), '../blog_tool/.env'))
        load_dotenv(blog_env_path)
        
        tg_token = os.getenv("TELEGRAM_BOT_TOKEN")
        tg_chat_id = os.getenv("TELEGRAM_CHAT_ID", os.getenv("TELEGRAM_ADMIN_CHAT_ID"))
        
        if tg_token and tg_chat_id:
            try:
                import io
                import requests
                short_kw = article.keyword[:100] + "..." if len(article.keyword) > 100 else article.keyword
                
                msg = f"✅ *Đã viết xong nội dung bài Blog!*\n\nTiêu đề: {short_kw}\n\n*Bạn hãy xem nội dung file Markdown đính kèm.*"
                md_content = getattr(article, "content_markdown", "No content")
                file_stream = io.BytesIO(md_content.encode('utf-8'))
                filename = f"blog_{article.id}.md"
                
                requests.post(
                    f"https://api.telegram.org/bot{tg_token}/sendDocument",
                    data={"chat_id": tg_chat_id, "caption": msg[:1000], "parse_mode": "Markdown"},
                    files={"document": (filename, file_stream, "text/markdown")}
                )
                
                # Gọi UI chọn Site hoặc Category
                if target_site:
                    from backend.workflow_engine import start_category_selection_workflow
                    start_category_selection_workflow(tg_chat_id, article_id, [target_site])
                else:
                    from backend.workflow_engine import start_site_selection_workflow
                    start_site_selection_workflow(tg_chat_id, article_id)
            except Exception as ex:
                print(f"Lỗi gửi thông báo Telegram: {ex}")
                
    except Exception as e:
        import traceback
        traceback.print_exc()
        print(f"Lỗi generate_blog_task: {e}")

@celery_app.task
def publish_blog_task(article_id: int, category_name: str = None):
    """Đăng bài lên WordPress dựa trên target_sites và target_category."""
    print(f"=== STARTING PUBLISH BLOG TASK FOR {article_id} ===")
    import sys
    import os
    import json
    blog_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '../blog_tool'))
    if blog_dir not in sys.path:
        sys.path.append(blog_dir)
        
    try:
        from database.session import init_db
        from database.models import ArticleStatus
        from services.article_repository import ArticleRepository
        from integrations.wordpress import WordPressPublisher
        from services.orchestrator import ArticleOrchestrator
        from llm_engine.agent import SEOAgent
        from dotenv import load_dotenv

        init_db()
        blog_env_path = os.path.abspath(os.path.join(blog_dir, '.env'))
        load_dotenv(blog_env_path)
        
        article = ArticleRepository.get_article_by_id(article_id)
        if not article:
            print("Article not found.")
            return
            
        target_sites = []
        if article.target_sites:
            try:
                target_sites = json.loads(article.target_sites)
            except:
                pass
                
        if not target_sites:
            print("No target sites configured.")
            return
            
        published_urls = []
        agent = SEOAgent()
        
        # Create dummy orchestrator to avoid passing invalid pub in constructor
        orchestrator = ArticleOrchestrator(agent=agent, wp_publisher=WordPressPublisher("https://dummy", "u", "p"))

        for site in target_sites:
            print(f"[*] Đang đẩy bài viết lên {site} vào category '{category_name}'...")
            wp_user = os.getenv(f"WP_USERNAME_{site}")
            wp_pass = os.getenv(f"WP_APP_PASSWORD_{site}")
            
            if not wp_user or not wp_pass:
                print(f"[!] Bỏ qua {site} vì thiếu cấu hình credentials trong .env")
                continue
                
            wp_pub = WordPressPublisher(site_url=f"https://{site}", username=wp_user, app_password=wp_pass)
            orchestrator.wp_publisher = wp_pub 
            
            is_pub_success, pub_msg, pub_url = orchestrator.publish_single_article(
                article_id=article_id,
                status_val="publish",
                category_id=None,
                category_name=category_name,
                thumbnail_bytes=None,
                thumbnail_name=None,
                thumbnail_details=None,
                content_markdown_processed=article.content_markdown
            )
            
            if is_pub_success:
                print(f"Publish success: {pub_url}")
                published_urls.append(pub_url)
            else:
                print(f"Publish failed for {site}: {pub_msg}")
                
        if published_urls:
            ArticleRepository.update_processing_state(article_id, ArticleStatus.PUBLISHED, f"Đã đăng lên {len(published_urls)} trang")
            if tg_token and tg_chat_id:
                try:
                    import io
                    short_kw = article.keyword[:100] + "..." if len(article.keyword) > 100 else article.keyword
                    
                    msg = f"✅ *Đã đăng bài Blog thành công!*\n\nTiêu đề: {short_kw}\n"
                    for u in published_urls:
                        msg += f"🔗 {u}\n"
                        
                    md_content = getattr(article, "content_markdown", "No content")
                    file_stream = io.BytesIO(md_content.encode('utf-8'))
                    filename = f"blog_{article.id}.md"
                    
                    import requests
                    requests.post(
                        f"https://api.telegram.org/bot{tg_token}/sendDocument",
                        data={"chat_id": tg_chat_id, "caption": msg[:1000], "parse_mode": "Markdown"},
                        files={"document": (filename, file_stream, "text/markdown")}
                    )
                except Exception as ex:
                    print(f"Lỗi gửi thông báo Telegram: {ex}")
        else:
            try:
                print(f"Publish failed: {pub_msg}")
            except UnicodeEncodeError:
                print(f"Publish failed: {str(pub_msg).encode('ascii', 'ignore').decode('ascii')}")
            ArticleRepository.update_processing_state(article_id, ArticleStatus.UPLOAD_FAILED, pub_msg)
            
            # Nếu đẩy thất bại thì vẫn gửi file MD về cho user
            tg_token = os.getenv("TELEGRAM_BOT_TOKEN")
            tg_chat_id = os.getenv("TELEGRAM_CHAT_ID", os.getenv("TELEGRAM_ADMIN_CHAT_ID"))
            if tg_token and tg_chat_id:
                try:
                    import io
                    short_kw = article.keyword[:100] + "..." if len(article.keyword) > 100 else article.keyword
                    msg = f"⚠️ *Đã viết xong Blog nhưng đăng lên Web lỗi!*\n\nTừ khoá: {short_kw}\nLỗi: {pub_msg}\n\n*Tuy nhiên bạn vẫn có thể tải nội dung Markdown ở file đính kèm để xem trước!*"
                    md_content = getattr(article, "content_markdown", "No content")
                    file_stream = io.BytesIO(md_content.encode('utf-8'))
                    filename = f"blog_{article.id}_failed.md"
                    
                    requests.post(
                        f"https://api.telegram.org/bot{tg_token}/sendDocument",
                        data={"chat_id": tg_chat_id, "caption": msg[:1000], "parse_mode": "Markdown"},
                        files={"document": (filename, file_stream, "text/markdown")}
                    )
                except Exception as ex:
                    pass
            
    except Exception as e:
        import traceback
        print(f"Error in auto_post_blog: {e}")
        traceback.print_exc()
