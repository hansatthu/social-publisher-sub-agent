import sys
import time
import os
import random
import urllib.parse
import json
import re
from playwright.sync_api import sync_playwright

def random_delay(min_sec=2, max_sec=4):
    time.sleep(random.uniform(min_sec, max_sec))

def run(playwright, keyword):
    import requests
    import socket
    cdp_host = os.getenv("CDP_HOST", "127.0.0.1:9222")
    print(f"👉 Đang kết nối tới Chrome ở {cdp_host}...")
    
    host_part = cdp_host
    port_part = "9222"
    if ":" in cdp_host:
        host_part, port_part = cdp_host.split(":", 1)
        
    if host_part == "host.docker.internal":
        try:
            host_part = socket.gethostbyname("host.docker.internal")
        except Exception:
            pass
            
    resolved_host = f"{host_part}:{port_part}"
    ws_url = None
    try:
        res = requests.get(f"http://{resolved_host}/json/version", timeout=2)
        if res.status_code == 200:
            ws_url = res.json().get("webSocketDebuggerUrl")
    except Exception as e:
        print(f"[!] Error resolving WebSocket URL: {e}")

    if not ws_url:
        print(f"❌ LỖI KẾT NỐI: Không thể cào/phân giải WebSocket URL ở {cdp_host} (IP: {host_part}).")
        return

    try:
        browser = playwright.chromium.connect_over_cdp(ws_url)
        context = browser.contexts[0] if browser.contexts else browser.new_context()
        page = context.new_page() # Luôn mở tab mới
        print("✅ Kết nối Chrome THÀNH CÔNG!")
    except Exception as e:
        print(f"❌ LỖI KẾT NỐI: Không thể kết nối tới Chrome ở {cdp_host}. Chi tiết: {e}")
        return

    encoded_keyword = urllib.parse.quote(keyword)
    search_url = f"https://www.facebook.com/search/groups/?q={encoded_keyword}"
    
    print(f"➡️ Đang mở trang tìm kiếm nhóm với từ khóa '{keyword}'...")
    page.goto(search_url)
    random_delay(5, 7)

    # Cuộn trang xuống 5 lần để tải thêm nhiều nhóm
    print("Đang cuộn trang xuống để load thêm nhóm...")
    for i in range(5):
        page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
        random_delay(1, 3)

    print("Đang phân tích trang để trích xuất link nhóm...")
    
    # Tìm tất cả các thẻ liên kết chứa đường dẫn nhóm
    # Facebook dùng đường dẫn dạng /groups/xxxxx/
    group_links = page.locator('a[href*="/groups/"]')
    count = group_links.count()
    
    crawled_results = {}
    
    for i in range(count):
        link_el = group_links.nth(i)
        try:
            href = link_el.get_attribute("href")
            if not href:
                continue
                
            # Chuẩn hóa link nhóm về dạng: https://www.facebook.com/groups/<group_id_or_name>/
            # Tránh lấy các link phụ như /groups/feed/, /groups/discover/, /groups/profile/
            match = re.search(r'facebook\.com/groups/([^/?#]+)', href)
            if match:
                group_id_or_name = match.group(1)
                # Bỏ qua các trang chức năng mặc định của Facebook
                if group_id_or_name in ['feed', 'discover', 'joins', 'create', 'categories', 'search']:
                    continue
                    
                group_url = f"https://www.facebook.com/groups/{group_id_or_name}/"
                
                # Lấy tên nhóm (thường là inner text của liên kết hoặc thẻ con bên trong nó)
                name = link_el.inner_text().strip()
                
                # Nếu tên quá ngắn hoặc rỗng, hoặc chứa thông số thành viên, ta sẽ bỏ qua
                # hoặc lấy tên nhóm từ phần tử heading gần nhất
                if not name or len(name) < 2 or "thành viên" in name or "members" in name:
                    continue
                
                # Lấy metadata thành viên và bài viết từ container
                members = "Không rõ"
                posts = "Không rõ"
                for depth in range(1, 6):
                    try:
                        parent_locator = link_el.locator(f"xpath=./ancestor::div[{depth}]")
                        txt = parent_locator.inner_text()
                        if "thành viên" in txt or "members" in txt:
                            # Parse metadata
                            members_match = re.search(r'([\d.,]+[KkMm]?)\s*(thành viên|members)', txt, re.IGNORECASE)
                            if members_match:
                                members = members_match.group(1)
                            
                            # Parse posts
                            # Tiếng Việt
                            posts_day_match = re.search(r'([\d.,]+)\s*bài viết\s*(một ngày|/ngày|mỗi ngày)', txt, re.IGNORECASE)
                            if posts_day_match:
                                posts = f"{posts_day_match.group(1)} bài/ngày"
                            else:
                                posts_month_match = re.search(r'([\d.,]+)\s*bài viết\s*(một tháng|/tháng|mỗi tháng)', txt, re.IGNORECASE)
                                if posts_month_match:
                                    posts = f"{posts_month_match.group(1)} bài/tháng"
                                else:
                                    posts_week_match = re.search(r'([\d.,]+)\s*bài viết\s*(một tuần|/tuần|mỗi tuần)', txt, re.IGNORECASE)
                                    if posts_week_match:
                                        posts = f"{posts_week_match.group(1)} bài/tuần"
                            
                            # Tiếng Anh
                            if posts == "Không rõ":
                                posts_day_en = re.search(r'([\d.,]+)\s*posts?\s*(a day|per day|daily)', txt, re.IGNORECASE)
                                if posts_day_en:
                                    posts = f"{posts_day_en.group(1)} bài/ngày"
                                else:
                                    posts_month_en = re.search(r'([\d.,]+)\s*posts?\s*(a month|per month|monthly)', txt, re.IGNORECASE)
                                    if posts_month_en:
                                        posts = f"{posts_month_en.group(1)} bài/tháng"
                                    else:
                                        posts_week_en = re.search(r'([\d.,]+)\s*posts?\s*(a week|per week|weekly)', txt, re.IGNORECASE)
                                        if posts_week_en:
                                            posts = f"{posts_week_en.group(1)} bài/tuần"
                            break
                    except:
                        pass

                # Tránh trùng lặp nhóm
                if group_url not in crawled_results:
                    crawled_results[group_url] = {
                        "name": name,
                        "url": group_url,
                        "members": members,
                        "posts": posts
                    }
        except Exception as e:
            continue

    # Đổi cấu trúc về dạng list
    results_list = list(crawled_results.values())
    
    # Lưu kết quả vào file json (phân chia theo keyword)
    script_dir = os.path.dirname(os.path.abspath(__file__))
    output_file_path = os.path.join(script_dir, "crawled_groups.json")
    
    data = {}
    if os.path.exists(output_file_path):
        try:
            with open(output_file_path, "r", encoding="utf-8") as f:
                existing_data = json.load(f)
                if isinstance(existing_data, dict):
                    data = existing_data
        except Exception:
            pass
            
    data[keyword] = results_list
    
    try:
        with open(output_file_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        print(f"✅ Đã quét xong! Tìm thấy {len(results_list)} nhóm cho từ khóa '{keyword}'.")
        print(f"Lưu danh sách tại: {output_file_path}")
    except Exception as e:
        print(f"❌ Lỗi ghi file json: {e}")

    try:
        page.close()
        print("ℹ️ Đã đóng tab tự động hóa.")
    except Exception as e:
        print(f"⚠️ Không thể đóng tab: {e}")

if __name__ == "__main__":
    keyword_input = sys.argv[1] if len(sys.argv) > 1 else "việc làm tây ninh"
    with sync_playwright() as p:
        run(p, keyword_input)
