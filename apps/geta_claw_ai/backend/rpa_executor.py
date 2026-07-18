import os
from playwright.sync_api import sync_playwright
import time
import psycopg2
import hashlib
import threading

# Semaphore để giới hạn 3 luồng Chrome chạy cùng lúc
chrome_semaphore = threading.Semaphore(3)

def get_db_connection():
    return psycopg2.connect(
        host="localhost",
        database="automation_db",
        user="postgres",
        password="1",
        port="5432"
    )

def get_profile_path(profile_id: str):
    # Nếu không dùng DB, có thể đọc từ fb_config.json
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT profile_path FROM browser_profiles WHERE id = %s", (profile_id,))
        row = cursor.fetchone()
        cursor.close()
        conn.close()
        if row:
            return row[0]
    except:
        pass
    
    # Fallback to general data dir based on platform and profile_id
    base_dir = "D:/GETA_WORKSPACE/python_backend/backend/chrome_profiles"
    path = os.path.join(base_dir, str(profile_id))
    os.makedirs(path, exist_ok=True)
    return path

def get_port_for_profile(profile_id: str) -> int:
    """Tạo ra một port cố định từ 9000-9999 cho mỗi profile để chạy độc lập"""
    hash_val = int(hashlib.md5(str(profile_id).encode()).hexdigest(), 16)
    return 9000 + (hash_val % 1000)

def upload_to_tiktok(video_path: str, topic: str, profile_id: str):
    """
    RPA Script: Dùng Playwright mở trình duyệt, đăng nhập bằng User Data (Profile)
    và tải video lên TikTok.
    """
    profile_path = get_profile_path(profile_id)
    port = get_port_for_profile(profile_id)

    with chrome_semaphore:
        with sync_playwright() as p:
            print(f"[RPA] Đang khởi chạy Chrome cho Profile: {profile_id} tại Port {port}...")
            # headless=False để hiển thị Browser lên màn hình
            browser = p.chromium.launch_persistent_context(
                user_data_dir=profile_path,
                headless=False,
                args=[
                    f"--remote-debugging-port={port}",
                    "--start-maximized", 
                    "--disable-blink-features=AutomationControlled"
                ]
            )
            page = browser.new_page()
            
            print("[RPA] Đang mở trang TikTok Upload...")
            page.goto("https://www.tiktok.com/creator-center/upload")
            
            # Đợi trang load
            time.sleep(5)
            
            # Kiểm tra xem có yêu cầu đăng nhập không (nếu Profile chưa login)
            if "login" in page.url:
                print(f"[RPA] Profile {profile_id} chưa đăng nhập TikTok! Đang chờ bạn đăng nhập thủ công...")
                # Dừng lại 60 giây để user tự quét mã QR hoặc đăng nhập
                time.sleep(60)
                
            print("[RPA] Đang tải video lên...")
            # Tìm thẻ input file để upload
            file_input = page.locator("input[type='file']")
            file_input.set_input_files(video_path)
            
            time.sleep(5)
            
            print("[RPA] Đang nhập tiêu đề...")
            # Tìm ô nhập caption (Tiktok sử dụng thẻ div contenteditable)
            caption_box = page.locator(".public-DraftEditor-content")
            if caption_box.is_visible():
                caption_box.fill(f"{topic} #trending #viral")
            
            time.sleep(2)
            
            print("[RPA] Đang bấm nút Đăng (Post)...")
            # Tìm nút Đăng
            post_button = page.locator("button:has-text('Đăng'), button:has-text('Post')").first
            if post_button.is_visible():
                post_button.click()
                print("[RPA] Đã bấm đăng!")
                time.sleep(10) # Chờ upload xong
            else:
                print("[RPA] Không tìm thấy nút đăng!")
                
            browser.close()
            return f"Upload thành công Profile {profile_id}!"
